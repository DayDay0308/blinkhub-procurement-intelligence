-- 0004: supplier compliance documents
--   * who uploaded a document, the original file name, type and size
--   * why a document was rejected (the supplier sees this)
--   * the same file can't be uploaded twice for one supplier
--   * fast lookup of a supplier's documents by type

ALTER TABLE compliance.documents
  ADD COLUMN uploaded_by       uuid REFERENCES core.users(id),
  ADD COLUMN original_filename varchar(200),
  ADD COLUMN content_type      varchar(100),
  ADD COLUMN size_bytes        integer CHECK (size_bytes IS NULL OR size_bytes > 0),
  ADD COLUMN rejection_reason  text,
  ADD CONSTRAINT ck_rejected_has_reason
    CHECK (status <> 'REJECTED' OR rejection_reason IS NOT NULL),
  ADD CONSTRAINT ck_verified_has_verifier
    CHECK (status <> 'VERIFIED' OR verified_at IS NOT NULL OR starts_with(storage_key, 'demo/') OR starts_with(storage_key, 'synthetic/'));

CREATE UNIQUE INDEX ux_documents_supplier_file ON compliance.documents (supplier_id, sha256);
CREATE INDEX ix_documents_supplier_type ON compliance.documents (supplier_id, doc_type, status);
