# Appointment Booking System: Service Implementation + MongoDB Schema Guide

This document is a handoff spec for implementing the three core services from the project architecture:

1. Resource Service
2. Booking Service
3. Notification Service

It defines what each service must do and the MongoDB schemas/indexes required.

## 1) Scope and Service Ownership

### Resource Service owns:
- Resource catalog (clinics/rooms/courts/etc.)
- Operating hours and slot settings
- Blackout dates / temporary closures
- Capacity defaults and per-day overrides

### Booking Service owns:
- Booking lifecycle (create/cancel/reschedule)
- Capacity enforcement and anti-overbooking logic
- Booking state/history
- Outbox events for downstream processing

### Notification Service owns:
- Reminder/confirmation scheduling
- Delivery attempts and status
- Notification templates/preferences

No service should write directly into another service database.

## 2) Cross-Service Flow (Required)

1. Client requests available slots.
2. Resource Service provides resource rules.
3. Booking Service returns available slots and accepts booking request.
4. Booking Service atomically reserves capacity and writes booking.
5. Booking Service emits event (`booking.created` / `booking.cancelled` / `booking.rescheduled`) via outbox.
6. Notification Service consumes events and creates notification jobs.
7. Notification Service dispatches confirmation/reminder notifications.

## 3) MongoDB Architecture Rules

- Use separate databases per service:
  - `resource_db`
  - `booking_db`
  - `notification_db`
- Use a MongoDB replica set so Booking Service can use transactions.
- Use UTC for all timestamps.
- Use ISODate for datetime fields.
- Add `createdAt` and `updatedAt` on every collection.
- Add optimistic concurrency where needed via `version` field.

## 4) Resource Service

## 4.1 Required API Capabilities

- Create/update/deactivate a resource
- Define operating hours and slot duration
- Add/remove blackout periods
- Set capacity defaults and date-level overrides
- Query bookable configuration by resource and date range

## 4.2 Collections

### `resources`

```json
{
  "_id": "ObjectId",
  "resourceCode": "string-unique",
  "name": "string",
  "type": "string",
  "location": {
    "site": "string",
    "building": "string",
    "floor": "string",
    "room": "string",
    "timezone": "string"
  },
  "status": "active|inactive|maintenance",
  "slotDurationMin": 30,
  "defaultCapacity": 1,
  "tags": ["string"],
  "metadata": {},
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ resourceCode: 1 }`
- query index: `{ status: 1, type: 1 }`
- optional text index on `name`

### `resource_schedules`

```json
{
  "_id": "ObjectId",
  "resourceId": "ObjectId",
  "dayOfWeek": 1,
  "openTime": "08:00",
  "closeTime": "18:00",
  "breaks": [
    { "startTime": "12:00", "endTime": "13:00" }
  ],
  "effectiveFrom": "ISODate",
  "effectiveTo": "ISODate|null",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- `{ resourceId: 1, dayOfWeek: 1, effectiveFrom: -1 }`

### `resource_blackouts`

```json
{
  "_id": "ObjectId",
  "resourceId": "ObjectId",
  "startAt": "ISODate",
  "endAt": "ISODate",
  "reason": "string",
  "createdBy": "string",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- `{ resourceId: 1, startAt: 1, endAt: 1 }`

### `resource_capacity_overrides`

```json
{
  "_id": "ObjectId",
  "resourceId": "ObjectId",
  "date": "ISODate-00:00:00Z",
  "capacity": 2,
  "reason": "string",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ resourceId: 1, date: 1 }`

## 5) Booking Service

## 5.1 Required API Capabilities

- Search availability by resource/date/time window
- Create booking
- Cancel booking
- Reschedule booking
- Fetch booking(s) by user

## 5.2 Core Correctness Requirement (No Overbooking)

For each `(resourceId, slotStartAt)` maintain a slot inventory record and reserve capacity atomically.

Atomic reserve filter must include capacity check in query:

```js
db.slot_inventory.findOneAndUpdate(
  {
    resourceId: <resourceId>,
    slotStartAt: <slotStartAt>,
    status: "open",
    $expr: { $lt: ["$reservedCount", "$capacity"] }
  },
  {
    $inc: { reservedCount: 1 },
    $set: { updatedAt: new Date() }
  },
  { returnDocument: "after" }
)
```

Implementation detail:
- Use this inside a transaction together with booking insert + outbox insert.
- If no document updated, booking must be rejected as slot full.

## 5.3 Collections

### `slot_inventory`

```json
{
  "_id": "ObjectId",
  "resourceId": "ObjectId",
  "slotStartAt": "ISODate",
  "slotEndAt": "ISODate",
  "capacity": 1,
  "reservedCount": 0,
  "status": "open|closed",
  "version": 1,
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ resourceId: 1, slotStartAt: 1 }`
- query index: `{ resourceId: 1, slotStartAt: 1, status: 1 }`

### `bookings`

```json
{
  "_id": "ObjectId",
  "bookingRef": "string-unique",
  "userId": "string",
  "username": "string",
  "resourceId": "ObjectId",
  "slotStartAt": "ISODate",
  "slotEndAt": "ISODate",
  "status": "confirmed|cancelled|rescheduled",
  "channel": "web|mobile|admin",
  "notes": "string",
  "rescheduledFromBookingId": "ObjectId|null",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ bookingRef: 1 }`
- `{ userId: 1, slotStartAt: -1 }`
- `{ resourceId: 1, slotStartAt: 1, status: 1 }`

### `idempotency_keys`

```json
{
  "_id": "ObjectId",
  "idempotencyKey": "string-unique",
  "operation": "create_booking|cancel_booking|reschedule_booking",
  "requestHash": "string",
  "response": {},
  "statusCode": 200,
  "expiresAt": "ISODate",
  "createdAt": "ISODate"
}
```

Indexes:
- unique: `{ idempotencyKey: 1 }`
- TTL: `{ expiresAt: 1 }`

### `booking_outbox`

```json
{
  "_id": "ObjectId",
  "eventId": "uuid-string-unique",
  "eventType": "booking.created|booking.cancelled|booking.rescheduled",
  "aggregateId": "bookingId",
  "payload": {},
  "status": "pending|published|failed",
  "attempts": 0,
  "nextAttemptAt": "ISODate",
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ eventId: 1 }`
- worker index: `{ status: 1, nextAttemptAt: 1 }`

## 5.4 Transaction Boundaries (Booking Service)

Create booking transaction must include:

1. Conditional increment on `slot_inventory`
2. Insert `bookings` document
3. Insert `booking_outbox` event

Cancel booking transaction must include:

1. Mark booking `cancelled` (if currently `confirmed`)
2. Decrement `slot_inventory.reservedCount` (never below 0)
3. Insert `booking_outbox` event

Reschedule booking can be:
- single transaction (release old slot + reserve new slot + booking update + outbox), or
- Saga with compensation (if scale/latency requires).

## 6) Notification Service

## 6.1 Required Capabilities

- Consume booking events
- Send confirmation immediately on booking creation
- Schedule reminders (e.g., 24h before, 2h before)
- Retry failed deliveries with backoff
- Track delivery outcomes

## 6.2 Collections

### `notification_preferences`

```json
{
  "_id": "ObjectId",
  "userId": "string-unique",
  "emailEnabled": true,
  "smsEnabled": false,
  "pushEnabled": true,
  "reminderOffsetsMin": [1440, 120],
  "quietHours": { "start": "22:00", "end": "07:00", "timezone": "Asia/Singapore" },
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ userId: 1 }`

### `notification_templates`

```json
{
  "_id": "ObjectId",
  "templateKey": "booking_confirmation_v1",
  "channel": "email|sms|push",
  "locale": "en-SG",
  "subject": "string",
  "body": "string-with-placeholders",
  "active": true,
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ templateKey: 1, channel: 1, locale: 1 }`

### `notification_jobs`

```json
{
  "_id": "ObjectId",
  "jobKey": "string-unique",
  "eventId": "uuid-string",
  "userId": "string",
  "bookingId": "ObjectId",
  "channel": "email|sms|push",
  "templateKey": "string",
  "scheduledAt": "ISODate",
  "status": "pending|processing|sent|failed|cancelled",
  "attempts": 0,
  "maxAttempts": 5,
  "nextAttemptAt": "ISODate",
  "payload": {},
  "createdAt": "ISODate",
  "updatedAt": "ISODate"
}
```

Indexes:
- unique: `{ jobKey: 1 }`
- worker index: `{ status: 1, nextAttemptAt: 1 }`
- query index: `{ userId: 1, scheduledAt: -1 }`

### `notification_deliveries`

```json
{
  "_id": "ObjectId",
  "jobId": "ObjectId",
  "provider": "ses|sns|twilio|fcm",
  "providerMessageId": "string",
  "attemptNo": 1,
  "status": "sent|failed",
  "errorCode": "string|null",
  "errorMessage": "string|null",
  "sentAt": "ISODate|null",
  "createdAt": "ISODate"
}
```

Indexes:
- `{ jobId: 1, attemptNo: 1 }`
- TTL (optional retention): `{ createdAt: 1 }` with `expireAfterSeconds`

## 7) Shared Event Contract (Booking -> Notification)

All events should use a common envelope:

```json
{
  "eventId": "uuid",
  "eventType": "booking.created",
  "eventVersion": 1,
  "occurredAt": "ISODate",
  "source": "booking-service",
  "traceId": "string",
  "data": {}
}
```

### `booking.created` `data`

```json
{
  "bookingId": "ObjectId",
  "bookingRef": "string",
  "userId": "string",
  "username": "string",
  "resourceId": "ObjectId",
  "resourceName": "string",
  "slotStartAt": "ISODate",
  "slotEndAt": "ISODate",
  "location": "string"
}
```

### `booking.cancelled` `data`

```json
{
  "bookingId": "ObjectId",
  "bookingRef": "string",
  "userId": "string",
  "cancelledAt": "ISODate",
  "reason": "string"
}
```

### `booking.rescheduled` `data`

```json
{
  "bookingId": "ObjectId",
  "bookingRef": "string",
  "userId": "string",
  "oldSlotStartAt": "ISODate",
  "newSlotStartAt": "ISODate",
  "newSlotEndAt": "ISODate"
}
```

## 8) Security + Auth Expectations

- Auth service remains separate.
- Service APIs expect `Authorization: Bearer <access_token>`.
- Parse claims: `username`, `role`, `exp`.
- Enforce role checks:
  - Admin-only: resource management endpoints
  - User: own bookings/preferences

## 9) Minimum Build Order

1. Resource Service collections + admin APIs
2. Booking Service inventory/booking transaction flow
3. Booking outbox publisher
4. Notification event consumer + job scheduler
5. Notification dispatcher with retry/backoff

## 10) Acceptance Checklist

### Resource Service
- Can create/update resources and schedules
- Blackout and capacity overrides are queryable by date

### Booking Service
- Parallel booking attempts never exceed slot capacity
- Cancel returns capacity correctly
- Reschedule updates inventory safely
- Idempotency key prevents duplicate booking writes

### Notification Service
- Confirmation is created for `booking.created`
- Reminders at configured offsets are scheduled
- Failed sends retry and eventually move to failed/cancelled state

---

If needed, split this into three separate docs (`resource-service.md`, `booking-service.md`, `notification-service.md`) and generate OpenAPI specs from the same contract.
