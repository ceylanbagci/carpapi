--
-- PostgreSQL database dump
--

\restrict AiMWwVIfVPCOPW5KLIOzxaWl7DrGVZcb5n1FJdbGAIIRlz4GEnEWRTMmHixIwwP

-- Dumped from database version 17.9 (Homebrew)
-- Dumped by pg_dump version 17.9 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: makes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.makes (id, slug, name, homepage_url, logo_url, created_at, updated_at) FROM stdin;
7d2f2dcf-0d3b-4ae5-8018-5f41c332f123	saturn	Saturn	\N	/media/logos/saturn.svg	2026-05-10 01:02:33.14322-04	2026-05-10 01:02:33.14322-04
2144fb4f-eeb6-45c6-a83d-203ecb8c4da3	acura	Acura	https://www.acura.com	/media/logos/acura.jpg	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
5dfac5ae-3eeb-45d9-a073-d24a748fd8d8	alfa-romeo	Alfa Romeo	https://www.alfaromeousa.com	/media/logos/alfa-romeo.jpg	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
0e328d6d-f553-4488-92bb-5d7faede742f	aston-martin	Aston Martin	https://www.astonmartin.com/en-us	/media/logos/aston-martin.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
c9a21d62-10cc-4a58-9fd2-afedadc5f0ca	audi	Audi	https://www.audiusa.com	/media/logos/audi.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
08e981b4-c25e-4311-a285-6b47d7a01673	bentley	Bentley	https://www.bentleymotors.com/en/usa.html	/media/logos/bentley.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
4b1d936c-a69c-4c88-963b-caf42a925022	bmw	BMW	https://www.bmwusa.com	/media/logos/bmw.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
8beafcbe-4eca-46cf-bba3-f43234bfc595	buick	Buick	https://www.buick.com	/media/logos/buick.jpg	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
4ecac48c-e250-4237-a103-2786ed9099ff	cadillac	CADILLAC	https://www.cadillac.com	/media/logos/cadillac.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
ddfe2202-b093-4281-8d1d-43e6636b6a36	chevrolet	Chevrolet	https://www.chevrolet.com	/media/logos/chevrolet.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
6042253b-d588-4086-add4-58e85516d537	chrysler	Chrysler	https://www.chrysler.com	/media/logos/chrysler.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
c952d6aa-5844-41ab-ab23-4ef162bf0ce9	dodge	Dodge	https://www.dodge.com	/media/logos/dodge.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
858354bc-93a5-4533-8a5d-c2353a216474	ferrari	Ferrari	https://www.ferrari.com/en-US	/media/logos/ferrari.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
9fd34f28-f7b6-43b7-a504-d9db0d25423e	fiat	FIAT	https://www.fiatusa.com	/media/logos/fiat.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
4745af7b-20c4-47dc-8720-93177edfb283	ford	Ford	https://www.ford.com	/media/logos/ford.jpg	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
c19fe720-8085-4aa0-94c4-b404d245f471	genesis	Genesis	https://www.genesis.com	/media/logos/genesis.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
12cbc991-0066-4dbb-9f3e-4a30c946999b	gmc	GMC	https://www.gmc.com	/media/logos/gmc.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
8846a57c-c318-4971-8c80-29a19ad9e724	honda	Honda	https://automobiles.honda.com	/media/logos/honda.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
ce6d1edd-b00f-486c-b0c3-d3a3f0dd679c	hyundai	Hyundai	https://www.hyundaiusa.com	/media/logos/hyundai.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
f01ca6fb-ed00-439a-9751-501f782f9b78	infiniti	INFINITI	https://www.infinitiusa.com	/media/logos/infiniti.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
5b9be5ca-beb6-49aa-a152-8a1a049ea560	jaguar	Jaguar	https://www.jaguarusa.com	/media/logos/jaguar.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
9e841cdf-d50e-4fca-bdc8-08566fec4090	jeep	Jeep	https://www.jeep.com	/media/logos/jeep.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
2fe9e0da-40c4-498d-965c-9d34217ee0d4	karma	Karma	https://www.karmaautomotive.com	/media/logos/karma.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
4c0fee71-89fc-4d59-8ae1-7c3cf645751e	kia	Kia	https://www.kia.com/us/en	/media/logos/kia.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
fe793eb1-be47-41ee-9528-c19f92d29be2	lamborghini	Lamborghini	https://www.lamborghini.com/en-en	/media/logos/lamborghini.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
d22a21a6-8356-4a53-b1a8-46977cda591b	land-rover	Land Rover	https://www.landroverusa.com	/media/logos/land-rover.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
c07ba905-dea2-4aa5-9486-29eb96140620	lexus	LEXUS	https://www.lexus.com	/media/logos/lexus.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
6175d1b8-e188-44d4-9dc1-cadabc3a5bea	lincoln	Lincoln	https://www.lincoln.com	/media/logos/lincoln.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
a3928639-dc65-4453-92a3-ae5b7fbcbdfb	lotus	Lotus	https://www.lotuscars.com/en-US	/media/logos/lotus.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
2f5f80a4-e337-4a90-bc5b-fcfbb8d862d4	maserati	Maserati	https://www.maserati.com/us/en	/media/logos/maserati.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
7c4168d4-e455-4399-a189-45936fe8c3d2	mazda	Mazda	https://www.mazdausa.com	/media/logos/mazda.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
ffeb685e-5847-4f23-8fae-3ffd0a7d2f7b	mclaren	Mclaren	https://cars.mclaren.com/us-en	/media/logos/mclaren.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
6dded37b-126b-4bf1-9242-17afe1c60492	mercedes-benz	Mercedes-Benz	https://www.mbusa.com	/media/logos/mercedes-benz.ico	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
3b6624b1-9590-41ef-826d-42a8f2e42e03	mini	MINI	https://www.miniusa.com	/media/logos/mini.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
d602b1d6-d8a9-40af-b4c1-0f61d667c68c	mitsubishi	Mitsubishi	https://www.mitsubishicars.com	/media/logos/mitsubishi.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
00777542-34ff-4ba8-bc1e-116bf255642c	nissan	Nissan	https://www.nissanusa.com	/media/logos/nissan.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
c0fe38a3-1d47-46c9-8f73-f28cb405b6b4	polestar	Polestar	https://www.polestar.com/us	/media/logos/polestar.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
eac7476c-9c41-4396-8643-5294a20d5049	porsche	Porsche	https://www.porsche.com/usa	/media/logos/porsche.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
48d3d511-ac98-4998-b5fd-e0e03dbb4716	ram	RAM	https://www.ramtrucks.com	/media/logos/ram.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
bdb2a9a9-6d67-42a5-95eb-262604cc26fa	rolls-royce	Rolls-Royce	https://www.rolls-roycemotorcars.com/en_US.html	/media/logos/rolls-royce.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
cc01cf17-4759-4343-828c-32c007669b12	saab	Saab	https://en.wikipedia.org/wiki/Saab_Automobile	/media/logos/saab.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
03259d4b-1683-40d1-b661-1e2d07e9764a	subaru	Subaru	https://www.subaru.com	/media/logos/subaru.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
2cb86cbc-e5bb-4297-9b18-043c1ef84c02	tesla	Tesla	https://www.tesla.com	/media/logos/tesla.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
c1292211-d0ae-42b3-a1f8-28fd658acdaa	toyota	Toyota	https://www.toyota.com	/media/logos/toyota.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
3380e362-1d7b-4e28-badd-4676a2cc6bb5	volkswagen	Volkswagen	https://www.vw.com	/media/logos/volkswagen.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
1f777181-c4c0-4398-9028-23bfcbcbb208	volvo	Volvo	https://www.volvocars.com/us	/media/logos/volvo.png	2026-05-10 01:02:33.14322-04	2026-05-10 01:13:53.27801-04
\.


--
-- PostgreSQL database dump complete
--

\unrestrict AiMWwVIfVPCOPW5KLIOzxaWl7DrGVZcb5n1FJdbGAIIRlz4GEnEWRTMmHixIwwP

