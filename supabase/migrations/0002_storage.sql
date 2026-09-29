-- =====================================================================
-- AI Knowledge Base — Supabase Storage
--
-- Private "documents" bucket for uploaded PDFs.
-- Object path convention: {user_id}/{document_id}.pdf
-- =====================================================================

-- Private bucket: files are never publicly addressable; the backend hands
-- out short-lived signed URLs instead. Size and MIME limits are enforced by
-- Storage itself, in addition to the backend's own validation.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('documents', 'documents', false, 20971520, array['application/pdf'])   -- 20 MB
on conflict (id) do update
    set public             = excluded.public,
        file_size_limit    = excluded.file_size_limit,
        allowed_mime_types = excluded.allowed_mime_types;


-- ---------------------------------------------------------------------
-- Row Level Security on storage.objects
-- ---------------------------------------------------------------------
-- Uploads and deletes go through the FastAPI backend (service role, which
-- bypasses RLS). A user's own JWT may only READ objects inside their own
-- top-level folder, i.e. {their user_id}/...

drop policy if exists "documents_bucket_select_own" on storage.objects;
create policy "documents_bucket_select_own" on storage.objects
    for select to authenticated
    using (
        bucket_id = 'documents'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );
