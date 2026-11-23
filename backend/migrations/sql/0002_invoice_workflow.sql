-- Migration 0002: invoice workflow support
--  * stored 3-way-match exceptions on invoices
--  * in-app notifications (SLA warnings, escalations, workflow events)

ALTER TABLE p2p.invoices
  ADD COLUMN match_exceptions text[] NOT NULL DEFAULT '{}';

CREATE TABLE core.notifications (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES core.users(id) ON DELETE CASCADE,
  kind         varchar(40) NOT NULL,          -- SLA_WARNING, SLA_ESCALATED, SLA_BREACHED, INVOICE_ASSIGNED, ...
  entity_type  varchar(30) NOT NULL,
  entity_id    uuid NOT NULL,
  title        varchar(200) NOT NULL,
  body         text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  read_at      timestamptz,
  UNIQUE (user_id, kind, entity_id)           -- the hourly SLA job never spams the same alert
);
CREATE INDEX ix_notifications_unread ON core.notifications (user_id) WHERE read_at IS NULL;
