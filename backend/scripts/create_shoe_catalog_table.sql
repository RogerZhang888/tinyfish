create extension if not exists "pgcrypto";

create table if not exists public.shoe_catalog (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    price integer,
    brand text not null check (brand in ('adidas', 'nike', 'puma', 'asics', 'hoka', 'saucony')),
    weight integer,
    "type" text[] not null default '{}',
    description text not null default '',
    image_source text not null default '',
    foot_shape text not null default 'neutral' check (foot_shape in ('wide', 'neutral', 'narrow')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (brand, name)
);

create or replace function public.set_updated_at_timestamp()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_shoe_catalog_updated_at on public.shoe_catalog;

create trigger trg_shoe_catalog_updated_at
before update on public.shoe_catalog
for each row
execute function public.set_updated_at_timestamp();

create index if not exists idx_shoe_catalog_brand on public.shoe_catalog (brand);
create index if not exists idx_shoe_catalog_foot_shape on public.shoe_catalog (foot_shape);
