--
-- PostgreSQL database dump
--

\restrict cHDNqjoTvARvM7A6JFJlerQUrgrtSWxg16OmXWikqNZNM64sQW9yoYAnRzvgRmS

-- Dumped from database version 17.9 (Homebrew)
-- Dumped by pg_dump version 17.9 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: dealers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dealers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    homepage_url text,
    inventory_url text,
    cms text,
    cms_signals jsonb,
    robots_allows_inventory boolean,
    region text,
    city text,
    postal_code text,
    latitude double precision,
    longitude double precision,
    makes_carried text[],
    status text DEFAULT 'active'::text NOT NULL,
    last_scraped_at timestamp with time zone,
    enrolled_at timestamp with time zone DEFAULT now() NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT dealers_status_check CHECK ((status = ANY (ARRAY['active'::text, 'paused'::text, 'blocked'::text])))
);


--
-- Name: listing_groups; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listing_groups (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    canonical_vin text,
    canonical_make text,
    canonical_model text,
    canonical_trim text,
    canonical_year integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: listing_price_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listing_price_history (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    listing_id uuid NOT NULL,
    price_amount numeric(12,2),
    currency text DEFAULT 'USD'::text NOT NULL,
    observed_at timestamp with time zone DEFAULT now() NOT NULL,
    source_id text,
    raw_checksum text
);


--
-- Name: listings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listings (
    id uuid NOT NULL,
    dedupe_key character varying(512) NOT NULL,
    source_id character varying(128) NOT NULL,
    source_name character varying(256) NOT NULL,
    external_id character varying(256) NOT NULL,
    listing_url text NOT NULL,
    title text NOT NULL,
    description text,
    make character varying(128),
    model character varying(128),
    "trim" character varying(128),
    year integer,
    body_style character varying(64),
    vin character varying(32),
    mileage double precision,
    mileage_unit character varying(8) NOT NULL,
    price_amount double precision,
    currency character varying(3) NOT NULL,
    monthly_payment_estimate double precision,
    seller_name character varying(256),
    seller_type character varying(32),
    latitude double precision,
    longitude double precision,
    region character varying(64),
    city character varying(128),
    postal_code character varying(32),
    listing_posted_at timestamp with time zone,
    listing_updated_at timestamp with time zone,
    scraped_at timestamp with time zone NOT NULL,
    raw_checksum character varying(128),
    features jsonb,
    images jsonb,
    raw_document jsonb,
    listing_group_id uuid,
    car_url text,
    dealer_id uuid,
    is_on_sale boolean DEFAULT false NOT NULL,
    price_refreshed_at timestamp with time zone,
    maker_url text,
    maker_specs jsonb,
    window_sticker jsonb,
    window_sticker_url text,
    maker_enriched_at timestamp with time zone,
    maker_enrich_status text,
    maker_enrich_error text,
    embedding public.vector(1024),
    CONSTRAINT ck_listings_maker_enrich_status CHECK (((maker_enrich_status IS NULL) OR (maker_enrich_status = ANY (ARRAY['pending'::text, 'enriched'::text, 'unsupported'::text, 'login_required'::text, 'failed'::text]))))
);


--
-- Name: makes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.makes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    homepage_url text,
    logo_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id text NOT NULL,
    name text NOT NULL,
    type text NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    license_terms text,
    ingest_cadence interval DEFAULT '1 day'::interval NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT sources_type_check CHECK ((type = ANY (ARRAY['api'::text, 'feed'::text, 'scrape'::text, 'fixture'::text])))
);


--
-- Name: dealers dealers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dealers
    ADD CONSTRAINT dealers_pkey PRIMARY KEY (id);


--
-- Name: dealers dealers_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dealers
    ADD CONSTRAINT dealers_slug_key UNIQUE (slug);


--
-- Name: listing_groups listing_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_groups
    ADD CONSTRAINT listing_groups_pkey PRIMARY KEY (id);


--
-- Name: listing_price_history listing_price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_price_history
    ADD CONSTRAINT listing_price_history_pkey PRIMARY KEY (id);


--
-- Name: listings listings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_pkey PRIMARY KEY (id);


--
-- Name: makes makes_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.makes
    ADD CONSTRAINT makes_name_key UNIQUE (name);


--
-- Name: makes makes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.makes
    ADD CONSTRAINT makes_pkey PRIMARY KEY (id);


--
-- Name: makes makes_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.makes
    ADD CONSTRAINT makes_slug_key UNIQUE (slug);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: listings uq_listings_dedupe_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT uq_listings_dedupe_key UNIQUE (dedupe_key);


--
-- Name: ix_dealers_cms; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dealers_cms ON public.dealers USING btree (cms);


--
-- Name: ix_dealers_makes_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dealers_makes_gin ON public.dealers USING gin (makes_carried);


--
-- Name: ix_dealers_region_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dealers_region_status ON public.dealers USING btree (region, status);


--
-- Name: ix_listing_groups_make_model_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listing_groups_make_model_year ON public.listing_groups USING btree (canonical_make, canonical_model, canonical_year);


--
-- Name: ix_listings_car_url; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_car_url ON public.listings USING btree (car_url);


--
-- Name: ix_listings_dealer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_dealer_id ON public.listings USING btree (dealer_id);


--
-- Name: ix_listings_dedupe_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_dedupe_key ON public.listings USING btree (dedupe_key);


--
-- Name: ix_listings_embedding_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_embedding_hnsw ON public.listings USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: ix_listings_enrich_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_enrich_pending ON public.listings USING btree (make) WHERE ((maker_specs IS NULL) AND ((maker_enrich_status IS NULL) OR (maker_enrich_status <> ALL (ARRAY['unsupported'::text, 'login_required'::text]))));


--
-- Name: ix_listings_is_on_sale; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_is_on_sale ON public.listings USING btree (is_on_sale) WHERE (is_on_sale = true);


--
-- Name: ix_listings_listing_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_listing_group_id ON public.listings USING btree (listing_group_id);


--
-- Name: ix_listings_make; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_make ON public.listings USING btree (make);


--
-- Name: ix_listings_make_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_make_model ON public.listings USING btree (make, model);


--
-- Name: ix_listings_model; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_model ON public.listings USING btree (model);


--
-- Name: ix_listings_price_amount; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_price_amount ON public.listings USING btree (price_amount);


--
-- Name: ix_listings_price_refreshed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_price_refreshed_at ON public.listings USING btree (price_refreshed_at);


--
-- Name: ix_listings_region; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_region ON public.listings USING btree (region);


--
-- Name: ix_listings_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_source_id ON public.listings USING btree (source_id);


--
-- Name: ix_listings_vin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_vin ON public.listings USING btree (vin);


--
-- Name: ix_listings_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_listings_year ON public.listings USING btree (year);


--
-- Name: ix_lph_listing_observed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lph_listing_observed ON public.listing_price_history USING btree (listing_id, observed_at DESC);


--
-- Name: ix_lph_observed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lph_observed ON public.listing_price_history USING btree (observed_at DESC);


--
-- Name: ix_makes_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_makes_name ON public.makes USING btree (name);


--
-- Name: ix_sources_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_sources_enabled ON public.sources USING btree (enabled);


--
-- Name: uq_listing_groups_canonical_vin; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_listing_groups_canonical_vin ON public.listing_groups USING btree (canonical_vin) WHERE (canonical_vin IS NOT NULL);


--
-- Name: listings fk_listings_dealer_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT fk_listings_dealer_id FOREIGN KEY (dealer_id) REFERENCES public.dealers(id) ON DELETE SET NULL;


--
-- Name: listings fk_listings_group_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT fk_listings_group_id FOREIGN KEY (listing_group_id) REFERENCES public.listing_groups(id) ON DELETE SET NULL;


--
-- Name: listing_price_history listing_price_history_listing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_price_history
    ADD CONSTRAINT listing_price_history_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict cHDNqjoTvARvM7A6JFJlerQUrgrtSWxg16OmXWikqNZNM64sQW9yoYAnRzvgRmS

