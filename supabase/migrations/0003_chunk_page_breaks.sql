-- =====================================================================
-- Page breaks inside chunks
-- =====================================================================
-- A chunk that crosses pages (page_number < page_end) records where each
-- later page begins in its content: [[offset, page], ...], offsets in
-- characters from the start of `content`. RAG marks those points in the
-- prompt, so the model can cite the exact page of a statement instead of
-- the whole range. NULL for single-page chunks and chunks stored before
-- this migration.

alter table public.document_chunks
    add column if not exists page_breaks jsonb;

-- Using the vector type loads the pgvector library in this session, which
-- registers hnsw.iterative_scan; without it, `set hnsw.iterative_scan`
-- below is rejected as an unknown parameter the role may not set.
select '[0]'::extensions.vector;

-- The return type changes, so the function must be dropped and recreated.
drop function if exists public.match_document_chunks(extensions.vector, uuid, integer, double precision);

create function public.match_document_chunks(
    query_embedding    extensions.vector(1536),
    match_document_id  uuid,
    match_count        integer default 5,
    min_similarity     double precision default 0
)
returns table (
    id           uuid,
    document_id  uuid,
    content      text,
    page_number  integer,
    page_end     integer,
    page_breaks  jsonb,
    chunk_index  integer,
    similarity   double precision
)
language sql
stable
set search_path = public, extensions
set hnsw.iterative_scan = relaxed_order
as $$
    select *
    from (
        select
            c.id,
            c.document_id,
            c.content,
            c.page_number,
            c.page_end,
            c.page_breaks,
            c.chunk_index,
            1 - (c.embedding <=> query_embedding) as similarity
        from public.document_chunks c
        where c.document_id = match_document_id
          and c.embedding is not null
        order by c.embedding <=> query_embedding
        limit least(greatest(match_count, 1), 50)
    ) ranked
    where ranked.similarity >= min_similarity
    order by ranked.similarity desc;
$$;

revoke execute on function public.match_document_chunks(extensions.vector, uuid, integer, double precision) from public, anon;
grant  execute on function public.match_document_chunks(extensions.vector, uuid, integer, double precision) to authenticated, service_role;
