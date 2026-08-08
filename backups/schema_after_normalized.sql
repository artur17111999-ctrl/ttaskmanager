--
-- PostgreSQL database dump
--


-- Dumped from database version 18.3
-- Dumped by pg_dump version 18.3

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
-- Name: pgagent; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA pgagent;


--
-- Name: SCHEMA pgagent; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA pgagent IS 'pgAgent system tables';


--
-- Name: pgagent; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgagent WITH SCHEMA pgagent;


--
-- Name: EXTENSION pgagent; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgagent IS 'A PostgreSQL job scheduler';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.accounts (
    id integer NOT NULL,
    login character varying(50) NOT NULL,
    password_hash character varying(255) NOT NULL,
    employee_id integer NOT NULL,
    is_locked boolean DEFAULT false,
    last_login timestamp without time zone,
    created_at timestamp without time zone DEFAULT now(),
    status character varying(30) DEFAULT 'active'::character varying NOT NULL,
    password_changed_at timestamp without time zone,
    session_generation integer DEFAULT 0 NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    last_login_at timestamp without time zone,
    email_verified_at timestamp without time zone
);


--
-- Name: accounts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: accounts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.accounts_id_seq OWNED BY public.accounts.id;


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id bigint NOT NULL,
    company_id integer,
    actor_employee_id integer,
    action character varying(100) NOT NULL,
    entity_type character varying(100) NOT NULL,
    entity_id text,
    old_values jsonb,
    new_values jsonb,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_audit_log_action_not_blank CHECK ((btrim((action)::text) <> ''::text)),
    CONSTRAINT ck_audit_log_entity_type_not_blank CHECK ((btrim((entity_type)::text) <> ''::text))
);


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_log_id_seq OWNED BY public.audit_log.id;


--
-- Name: chat_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chat_members (
    chat_id integer NOT NULL,
    employee_id integer NOT NULL,
    joined_at timestamp without time zone DEFAULT now()
);


--
-- Name: chats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chats (
    id integer NOT NULL,
    name character varying(255),
    is_group boolean DEFAULT false,
    created_by integer,
    created_at timestamp without time zone DEFAULT now(),
    is_self boolean DEFAULT false,
    company_id integer
);


--
-- Name: chats_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chats_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chats_id_seq OWNED BY public.chats.id;


--
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    inn character varying(12) NOT NULL,
    kpp character varying(9),
    legal_address text,
    actual_address text,
    contact_email character varying(255),
    website_url character varying(500),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    task_catalog_version bigint DEFAULT 1 NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    archived_at timestamp without time zone,
    owner_employee_id integer,
    employee_limit integer DEFAULT 15 NOT NULL,
    plan_code character varying(50) DEFAULT 'default'::character varying NOT NULL,
    CONSTRAINT ck_companies_inn_format CHECK (((inn)::text ~ '^[0-9]{10}([0-9]{2})?$'::text)),
    CONSTRAINT ck_companies_kpp_format CHECK (((kpp IS NULL) OR ((kpp)::text ~ '^[0-9]{9}$'::text))),
    CONSTRAINT ck_companies_name_not_blank CHECK ((btrim((name)::text) <> ''::text)),
    CONSTRAINT ck_companies_status CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('blocked'::character varying)::text, ('archived'::character varying)::text])))
);


--
-- Name: companies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.companies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: companies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.companies_id_seq OWNED BY public.companies.id;


--
-- Name: company_invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_invitations (
    id bigint NOT NULL,
    company_id integer NOT NULL,
    email_normalized character varying(320) NOT NULL,
    requested_role character varying(50) DEFAULT 'employee'::character varying NOT NULL,
    token_hash character varying(128) NOT NULL,
    invited_by integer NOT NULL,
    profile_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    accepted_at timestamp without time zone,
    revoked_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    accepted_employee_id integer,
    accepted_account_id integer,
    superseded_by_id bigint,
    last_sent_at timestamp without time zone,
    delivery_status character varying(30) DEFAULT 'manual'::character varying NOT NULL,
    acceptance_request_id character varying(100),
    CONSTRAINT ck_company_invitations_email_normalized CHECK ((((email_normalized)::text = lower(btrim((email_normalized)::text))) AND (btrim((email_normalized)::text) <> ''::text))),
    CONSTRAINT ck_company_invitations_expiration CHECK ((expires_at > created_at)),
    CONSTRAINT ck_company_invitations_requested_role CHECK (((requested_role)::text = ANY (ARRAY[('employee'::character varying)::text, ('company_admin'::character varying)::text]))),
    CONSTRAINT ck_company_invitations_terminal_state CHECK ((NOT ((accepted_at IS NOT NULL) AND (revoked_at IS NOT NULL)))),
    CONSTRAINT ck_company_invitations_token_hash_not_blank CHECK ((btrim((token_hash)::text) <> ''::text))
);


--
-- Name: company_invitations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_invitations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_invitations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_invitations_id_seq OWNED BY public.company_invitations.id;


--
-- Name: company_membership_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_membership_history (
    id bigint NOT NULL,
    company_id integer NOT NULL,
    employee_id integer NOT NULL,
    role character varying(50) NOT NULL,
    membership_status character varying(30) DEFAULT 'active'::character varying NOT NULL,
    source_invitation_id bigint,
    changed_by integer,
    reason text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    started_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    ended_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_company_membership_history_period CHECK (((ended_at IS NULL) OR (ended_at >= started_at))),
    CONSTRAINT ck_company_membership_history_role CHECK (((role)::text = ANY (ARRAY[('employee'::character varying)::text, ('company_admin'::character varying)::text, ('company_owner'::character varying)::text]))),
    CONSTRAINT ck_company_membership_history_status CHECK (((membership_status)::text = ANY (ARRAY[('active'::character varying)::text, ('dismissed'::character varying)::text, ('blocked'::character varying)::text])))
);


--
-- Name: company_membership_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.company_membership_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: company_membership_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.company_membership_history_id_seq OWNED BY public.company_membership_history.id;


--
-- Name: departments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.departments (
    id integer NOT NULL,
    title character varying(255) NOT NULL
);


--
-- Name: departments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.departments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: departments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.departments_id_seq OWNED BY public.departments.id;


--
-- Name: drafts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.drafts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    chat_id integer NOT NULL,
    text text DEFAULT ''::text NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: drafts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.drafts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: drafts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.drafts_id_seq OWNED BY public.drafts.id;


--
-- Name: employees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employees (
    id integer NOT NULL,
    last_name character varying(100) NOT NULL,
    first_name character varying(100) NOT NULL,
    middle_name character varying(100),
    birth_date date NOT NULL,
    start_date date NOT NULL,
    is_dismissed boolean DEFAULT false,
    position_id integer NOT NULL,
    department_id integer NOT NULL,
    email character varying(255),
    company_id integer,
    role character varying(50) DEFAULT 'employee'::character varying NOT NULL
);


--
-- Name: employees_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.employees_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: employees_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.employees_id_seq OWNED BY public.employees.id;


--
-- Name: idempotency_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.idempotency_requests (
    id bigint NOT NULL,
    operation character varying(100) NOT NULL,
    key_hash character varying(128) NOT NULL,
    invitation_id bigint,
    principal_employee_id integer,
    request_hash character varying(128) NOT NULL,
    response_code integer,
    response_body jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    CONSTRAINT ck_idempotency_requests_expiration CHECK ((expires_at > created_at)),
    CONSTRAINT ck_idempotency_requests_key_hash CHECK (((key_hash)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_idempotency_requests_operation_not_blank CHECK ((btrim((operation)::text) <> ''::text)),
    CONSTRAINT ck_idempotency_requests_request_hash CHECK (((request_hash)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_idempotency_requests_response_code CHECK (((response_code IS NULL) OR ((response_code >= 100) AND (response_code <= 599))))
);


--
-- Name: idempotency_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.idempotency_requests_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: idempotency_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.idempotency_requests_id_seq OWNED BY public.idempotency_requests.id;


--
-- Name: image_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.image_attachments (
    id integer NOT NULL,
    owner_type character varying(20) NOT NULL,
    owner_id integer NOT NULL,
    image_data bytea NOT NULL,
    file_name character varying(255) DEFAULT 'screenshot.png'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT image_attachments_owner_type_check CHECK (((owner_type)::text = ANY (ARRAY[('task'::character varying)::text, ('message'::character varying)::text, ('comment'::character varying)::text])))
);


--
-- Name: image_attachments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.image_attachments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: image_attachments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.image_attachments_id_seq OWNED BY public.image_attachments.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    chat_id integer,
    sender_id integer,
    message_text text NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    is_read boolean DEFAULT false,
    is_deleted boolean DEFAULT false,
    edited_at timestamp without time zone,
    is_forwarded boolean DEFAULT false,
    forwarded_from character varying(255),
    forwarded_at timestamp without time zone
);


--
-- Name: COLUMN messages.is_forwarded; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.messages.is_forwarded IS 'Флаг indicating что сообщение является пересланным';


--
-- Name: COLUMN messages.forwarded_from; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.messages.forwarded_from IS 'Имя отправителя оригинального сообщения';


--
-- Name: COLUMN messages.forwarded_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.messages.forwarded_at IS 'Время пересылки сообщения';


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    chat_id integer,
    message_id integer,
    type character varying(50) DEFAULT 'new_message'::character varying NOT NULL,
    text text NOT NULL,
    is_read boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
);


--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: pinned_chats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pinned_chats (
    user_id integer NOT NULL,
    chat_id integer NOT NULL,
    pinned_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: positions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.positions (
    id integer NOT NULL,
    title character varying(255) NOT NULL
);


--
-- Name: positions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.positions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: positions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.positions_id_seq OWNED BY public.positions.id;


--
-- Name: stickies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stickies (
    id integer NOT NULL,
    user_id integer NOT NULL,
    source_type character varying(20) NOT NULL,
    source_id integer NOT NULL,
    title character varying(255) DEFAULT ''::character varying NOT NULL,
    text text DEFAULT ''::text NOT NULL,
    color character varying(20) DEFAULT '#fef3a5'::character varying NOT NULL,
    pin_mode character varying(30) DEFAULT 'bottom_movable'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    pos_x integer,
    pos_y integer,
    width integer DEFAULT 340 NOT NULL,
    height integer DEFAULT 274 NOT NULL,
    is_hidden boolean DEFAULT false NOT NULL,
    is_archived boolean DEFAULT false NOT NULL,
    company_id integer
);


--
-- Name: stickies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.stickies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: stickies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.stickies_id_seq OWNED BY public.stickies.id;


--
-- Name: task_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_comments (
    id integer NOT NULL,
    task_id integer NOT NULL,
    author_id integer NOT NULL,
    comment_text text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: task_comments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_comments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_comments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_comments_id_seq OWNED BY public.task_comments.id;


--
-- Name: task_files; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_files (
    id integer NOT NULL,
    task_id integer NOT NULL,
    file_name character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    file_size bigint,
    uploaded_by integer NOT NULL,
    uploaded_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: task_files_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_files_id_seq OWNED BY public.task_files.id;


--
-- Name: task_observers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_observers (
    id integer NOT NULL,
    task_id integer NOT NULL,
    employee_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: task_observers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_observers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_observers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_observers_id_seq OWNED BY public.task_observers.id;


--
-- Name: task_priorities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_priorities (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    title character varying(100) NOT NULL,
    color character varying(7) DEFAULT '#808080'::character varying,
    sort_order integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: task_priorities_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_priorities_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_priorities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_priorities_id_seq OWNED BY public.task_priorities.id;


--
-- Name: task_statuses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_statuses (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    title character varying(100) NOT NULL,
    color character varying(7) DEFAULT '#808080'::character varying,
    sort_order integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    company_id integer
);


--
-- Name: task_statuses_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_statuses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_statuses_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_statuses_id_seq OWNED BY public.task_statuses.id;


--
-- Name: task_tags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_tags (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    color character varying(7) DEFAULT '#808080'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    company_id integer
);


--
-- Name: task_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_tags_id_seq OWNED BY public.task_tags.id;


--
-- Name: task_tags_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_tags_link (
    id integer NOT NULL,
    task_id integer NOT NULL,
    tag_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    company_id integer
);


--
-- Name: task_tags_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_tags_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_tags_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_tags_link_id_seq OWNED BY public.task_tags_link.id;


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tasks (
    id integer NOT NULL,
    title character varying(500) NOT NULL,
    description text,
    status character varying(50) DEFAULT 'new'::character varying,
    priority character varying(50) DEFAULT 'Средний'::character varying,
    deadline date,
    author_id integer NOT NULL,
    executor_id integer NOT NULL,
    created_by integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    status_id integer,
    priority_id integer,
    short_description text,
    company_id integer
);


--
-- Name: tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tasks_id_seq OWNED BY public.tasks.id;


--
-- Name: accounts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts ALTER COLUMN id SET DEFAULT nextval('public.accounts_id_seq'::regclass);


--
-- Name: audit_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ALTER COLUMN id SET DEFAULT nextval('public.audit_log_id_seq'::regclass);


--
-- Name: chats id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chats ALTER COLUMN id SET DEFAULT nextval('public.chats_id_seq'::regclass);


--
-- Name: companies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies ALTER COLUMN id SET DEFAULT nextval('public.companies_id_seq'::regclass);


--
-- Name: company_invitations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations ALTER COLUMN id SET DEFAULT nextval('public.company_invitations_id_seq'::regclass);


--
-- Name: company_membership_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_membership_history ALTER COLUMN id SET DEFAULT nextval('public.company_membership_history_id_seq'::regclass);


--
-- Name: departments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments ALTER COLUMN id SET DEFAULT nextval('public.departments_id_seq'::regclass);


--
-- Name: drafts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drafts ALTER COLUMN id SET DEFAULT nextval('public.drafts_id_seq'::regclass);


--
-- Name: employees id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees ALTER COLUMN id SET DEFAULT nextval('public.employees_id_seq'::regclass);


--
-- Name: idempotency_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_requests ALTER COLUMN id SET DEFAULT nextval('public.idempotency_requests_id_seq'::regclass);


--
-- Name: image_attachments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_attachments ALTER COLUMN id SET DEFAULT nextval('public.image_attachments_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: positions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions ALTER COLUMN id SET DEFAULT nextval('public.positions_id_seq'::regclass);


--
-- Name: stickies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stickies ALTER COLUMN id SET DEFAULT nextval('public.stickies_id_seq'::regclass);


--
-- Name: task_comments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comments ALTER COLUMN id SET DEFAULT nextval('public.task_comments_id_seq'::regclass);


--
-- Name: task_files id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_files ALTER COLUMN id SET DEFAULT nextval('public.task_files_id_seq'::regclass);


--
-- Name: task_observers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_observers ALTER COLUMN id SET DEFAULT nextval('public.task_observers_id_seq'::regclass);


--
-- Name: task_priorities id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_priorities ALTER COLUMN id SET DEFAULT nextval('public.task_priorities_id_seq'::regclass);


--
-- Name: task_statuses id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_statuses ALTER COLUMN id SET DEFAULT nextval('public.task_statuses_id_seq'::regclass);


--
-- Name: task_tags id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags ALTER COLUMN id SET DEFAULT nextval('public.task_tags_id_seq'::regclass);


--
-- Name: task_tags_link id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags_link ALTER COLUMN id SET DEFAULT nextval('public.task_tags_link_id_seq'::regclass);


--
-- Name: tasks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks ALTER COLUMN id SET DEFAULT nextval('public.tasks_id_seq'::regclass);


--
-- Name: accounts accounts_employee_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_employee_id_key UNIQUE (employee_id);


--
-- Name: accounts accounts_login_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_login_key UNIQUE (login);


--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: chat_members chat_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_members
    ADD CONSTRAINT chat_members_pkey PRIMARY KEY (chat_id, employee_id);


--
-- Name: chats chats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT chats_pkey PRIMARY KEY (id);


--
-- Name: accounts ck_accounts_login_not_blank; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.accounts
    ADD CONSTRAINT ck_accounts_login_not_blank CHECK ((btrim((login)::text) <> ''::text)) NOT VALID;


--
-- Name: accounts ck_accounts_session_generation; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.accounts
    ADD CONSTRAINT ck_accounts_session_generation CHECK ((session_generation >= 0)) NOT VALID;


--
-- Name: accounts ck_accounts_status; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.accounts
    ADD CONSTRAINT ck_accounts_status CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('active'::character varying)::text, ('blocked'::character varying)::text]))) NOT VALID;


--
-- Name: companies ck_companies_employee_limit; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.companies
    ADD CONSTRAINT ck_companies_employee_limit CHECK ((employee_limit > 0)) NOT VALID;


--
-- Name: companies ck_companies_plan_code_not_blank; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.companies
    ADD CONSTRAINT ck_companies_plan_code_not_blank CHECK ((btrim((plan_code)::text) <> ''::text)) NOT VALID;


--
-- Name: company_invitations ck_company_invitations_acceptance_complete; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.company_invitations
    ADD CONSTRAINT ck_company_invitations_acceptance_complete CHECK ((((accepted_at IS NULL) AND (accepted_employee_id IS NULL) AND (accepted_account_id IS NULL)) OR ((accepted_at IS NOT NULL) AND (accepted_employee_id IS NOT NULL) AND (accepted_account_id IS NOT NULL)))) NOT VALID;


--
-- Name: company_invitations ck_company_invitations_acceptance_request_not_blank; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.company_invitations
    ADD CONSTRAINT ck_company_invitations_acceptance_request_not_blank CHECK (((acceptance_request_id IS NULL) OR (btrim((acceptance_request_id)::text) <> ''::text))) NOT VALID;


--
-- Name: company_invitations ck_company_invitations_delivery_status_not_blank; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.company_invitations
    ADD CONSTRAINT ck_company_invitations_delivery_status_not_blank CHECK ((btrim((delivery_status)::text) <> ''::text)) NOT VALID;


--
-- Name: company_invitations ck_company_invitations_not_self_superseded; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.company_invitations
    ADD CONSTRAINT ck_company_invitations_not_self_superseded CHECK (((superseded_by_id IS NULL) OR (superseded_by_id <> id))) NOT VALID;


--
-- Name: employees ck_employees_role; Type: CHECK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE public.employees
    ADD CONSTRAINT ck_employees_role CHECK (((role)::text = ANY (ARRAY[('employee'::character varying)::text, ('company_admin'::character varying)::text, ('company_owner'::character varying)::text, ('system_admin'::character varying)::text]))) NOT VALID;


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: company_invitations company_invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT company_invitations_pkey PRIMARY KEY (id);


--
-- Name: company_membership_history company_membership_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_membership_history
    ADD CONSTRAINT company_membership_history_pkey PRIMARY KEY (id);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: departments departments_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_title_key UNIQUE (title);


--
-- Name: drafts drafts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drafts
    ADD CONSTRAINT drafts_pkey PRIMARY KEY (id);


--
-- Name: drafts drafts_user_id_chat_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drafts
    ADD CONSTRAINT drafts_user_id_chat_id_key UNIQUE (user_id, chat_id);


--
-- Name: employees employees_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_email_key UNIQUE (email);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: idempotency_requests idempotency_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_requests
    ADD CONSTRAINT idempotency_requests_pkey PRIMARY KEY (id);


--
-- Name: image_attachments image_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.image_attachments
    ADD CONSTRAINT image_attachments_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: pinned_chats pinned_chats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pinned_chats
    ADD CONSTRAINT pinned_chats_pkey PRIMARY KEY (user_id, chat_id);


--
-- Name: positions positions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_pkey PRIMARY KEY (id);


--
-- Name: positions positions_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.positions
    ADD CONSTRAINT positions_title_key UNIQUE (title);


--
-- Name: stickies stickies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_pkey PRIMARY KEY (id);


--
-- Name: task_comments task_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comments
    ADD CONSTRAINT task_comments_pkey PRIMARY KEY (id);


--
-- Name: task_files task_files_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_files
    ADD CONSTRAINT task_files_pkey PRIMARY KEY (id);


--
-- Name: task_observers task_observers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_observers
    ADD CONSTRAINT task_observers_pkey PRIMARY KEY (id);


--
-- Name: task_observers task_observers_task_id_employee_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_observers
    ADD CONSTRAINT task_observers_task_id_employee_id_key UNIQUE (task_id, employee_id);


--
-- Name: task_priorities task_priorities_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_priorities
    ADD CONSTRAINT task_priorities_code_key UNIQUE (code);


--
-- Name: task_priorities task_priorities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_priorities
    ADD CONSTRAINT task_priorities_pkey PRIMARY KEY (id);


--
-- Name: task_statuses task_statuses_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_statuses
    ADD CONSTRAINT task_statuses_code_key UNIQUE (code);


--
-- Name: task_statuses task_statuses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_statuses
    ADD CONSTRAINT task_statuses_pkey PRIMARY KEY (id);


--
-- Name: task_tags_link task_tags_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags_link
    ADD CONSTRAINT task_tags_link_pkey PRIMARY KEY (id);


--
-- Name: task_tags_link task_tags_link_task_id_tag_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags_link
    ADD CONSTRAINT task_tags_link_task_id_tag_id_key UNIQUE (task_id, tag_id);


--
-- Name: task_tags task_tags_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags
    ADD CONSTRAINT task_tags_name_key UNIQUE (name);


--
-- Name: task_tags task_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags
    ADD CONSTRAINT task_tags_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: idx_audit_log_action_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_action_created ON public.audit_log USING btree (action, created_at DESC);


--
-- Name: idx_audit_log_actor_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_actor_created ON public.audit_log USING btree (actor_employee_id, created_at DESC);


--
-- Name: idx_audit_log_company_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_company_created ON public.audit_log USING btree (company_id, created_at DESC);


--
-- Name: idx_audit_log_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_log_entity ON public.audit_log USING btree (entity_type, entity_id, created_at DESC);


--
-- Name: idx_chat_members_employee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chat_members_employee ON public.chat_members USING btree (employee_id);


--
-- Name: idx_chats_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chats_company_id ON public.chats USING btree (company_id);


--
-- Name: idx_companies_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_companies_status ON public.companies USING btree (status);


--
-- Name: idx_company_invitations_accepted_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_invitations_accepted_account ON public.company_invitations USING btree (accepted_account_id) WHERE (accepted_account_id IS NOT NULL);


--
-- Name: idx_company_invitations_company_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_invitations_company_created ON public.company_invitations USING btree (company_id, created_at DESC);


--
-- Name: idx_company_invitations_delivery_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_invitations_delivery_status ON public.company_invitations USING btree (company_id, delivery_status, created_at DESC);


--
-- Name: idx_company_invitations_pending_expiration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_invitations_pending_expiration ON public.company_invitations USING btree (company_id, expires_at) WHERE ((accepted_at IS NULL) AND (revoked_at IS NULL));


--
-- Name: idx_company_invitations_superseded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_invitations_superseded_by ON public.company_invitations USING btree (superseded_by_id) WHERE (superseded_by_id IS NOT NULL);


--
-- Name: idx_company_membership_history_company_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_membership_history_company_started ON public.company_membership_history USING btree (company_id, started_at DESC);


--
-- Name: idx_company_membership_history_employee_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_membership_history_employee_started ON public.company_membership_history USING btree (employee_id, started_at DESC);


--
-- Name: idx_employees_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_employees_company_id ON public.employees USING btree (company_id);


--
-- Name: idx_idempotency_requests_expiration; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_idempotency_requests_expiration ON public.idempotency_requests USING btree (expires_at);


--
-- Name: idx_idempotency_requests_invitation_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_idempotency_requests_invitation_created ON public.idempotency_requests USING btree (invitation_id, created_at DESC) WHERE (invitation_id IS NOT NULL);


--
-- Name: idx_image_attachments_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_image_attachments_owner ON public.image_attachments USING btree (owner_type, owner_id);


--
-- Name: idx_messages_chat_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_chat_time ON public.messages USING btree (chat_id, created_at);


--
-- Name: idx_messages_is_forwarded; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_messages_is_forwarded ON public.messages USING btree (is_forwarded);


--
-- Name: idx_notifications_user_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_notifications_user_unread ON public.notifications USING btree (user_id, is_read, created_at DESC);


--
-- Name: idx_stickies_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stickies_company_id ON public.stickies USING btree (company_id);


--
-- Name: idx_stickies_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stickies_user ON public.stickies USING btree (user_id);


--
-- Name: idx_task_comments_author; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_comments_author ON public.task_comments USING btree (author_id);


--
-- Name: idx_task_comments_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_comments_created_at ON public.task_comments USING btree (created_at);


--
-- Name: idx_task_comments_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_comments_task ON public.task_comments USING btree (task_id);


--
-- Name: idx_task_observers_employee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_observers_employee ON public.task_observers USING btree (employee_id);


--
-- Name: idx_task_observers_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_observers_task ON public.task_observers USING btree (task_id);


--
-- Name: idx_task_statuses_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_statuses_company_id ON public.task_statuses USING btree (company_id);


--
-- Name: idx_task_tags_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_tags_company_id ON public.task_tags USING btree (company_id);


--
-- Name: idx_task_tags_link_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_tags_link_company_id ON public.task_tags_link USING btree (company_id);


--
-- Name: idx_task_tags_link_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_tags_link_tag ON public.task_tags_link USING btree (tag_id);


--
-- Name: idx_task_tags_link_task; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_tags_link_task ON public.task_tags_link USING btree (task_id);


--
-- Name: idx_tasks_author; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_author ON public.tasks USING btree (author_id);


--
-- Name: idx_tasks_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_company_id ON public.tasks USING btree (company_id);


--
-- Name: idx_tasks_deadline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_deadline ON public.tasks USING btree (deadline);


--
-- Name: idx_tasks_executor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_executor ON public.tasks USING btree (executor_id);


--
-- Name: idx_tasks_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_priority ON public.tasks USING btree (priority);


--
-- Name: idx_tasks_priority_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_priority_id ON public.tasks USING btree (priority_id);


--
-- Name: idx_tasks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_status ON public.tasks USING btree (status);


--
-- Name: idx_tasks_status_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tasks_status_id ON public.tasks USING btree (status_id);


--
-- Name: uq_accounts_id_employee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_accounts_id_employee_id ON public.accounts USING btree (id, employee_id);


--
-- Name: uq_accounts_login_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_accounts_login_normalized ON public.accounts USING btree (lower(btrim((login)::text)));


--
-- Name: uq_companies_inn_kpp; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_companies_inn_kpp ON public.companies USING btree (inn, kpp) WHERE (kpp IS NOT NULL);


--
-- Name: uq_companies_inn_without_kpp; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_companies_inn_without_kpp ON public.companies USING btree (inn) WHERE (kpp IS NULL);


--
-- Name: uq_companies_owner_employee; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_companies_owner_employee ON public.companies USING btree (owner_employee_id) WHERE (owner_employee_id IS NOT NULL);


--
-- Name: uq_company_invitations_acceptance_request; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_company_invitations_acceptance_request ON public.company_invitations USING btree (acceptance_request_id) WHERE (acceptance_request_id IS NOT NULL);


--
-- Name: uq_company_invitations_accepted_employee; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_company_invitations_accepted_employee ON public.company_invitations USING btree (accepted_employee_id) WHERE (accepted_employee_id IS NOT NULL);


--
-- Name: uq_company_invitations_pending_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_company_invitations_pending_email ON public.company_invitations USING btree (company_id, email_normalized) WHERE ((accepted_at IS NULL) AND (revoked_at IS NULL));


--
-- Name: uq_company_invitations_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_company_invitations_token_hash ON public.company_invitations USING btree (token_hash);


--
-- Name: uq_company_membership_history_open_employee; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_company_membership_history_open_employee ON public.company_membership_history USING btree (employee_id) WHERE (ended_at IS NULL);


--
-- Name: uq_employees_email_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_employees_email_normalized ON public.employees USING btree (lower(btrim((email)::text))) WHERE ((email IS NOT NULL) AND (btrim((email)::text) <> ''::text));


--
-- Name: uq_employees_id_company_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_employees_id_company_id ON public.employees USING btree (id, company_id);


--
-- Name: uq_idempotency_requests_operation_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_idempotency_requests_operation_key ON public.idempotency_requests USING btree (operation, key_hash);


--
-- Name: accounts accounts_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE CASCADE;


--
-- Name: chat_members chat_members_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_members
    ADD CONSTRAINT chat_members_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id) ON DELETE CASCADE;


--
-- Name: chat_members chat_members_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chat_members
    ADD CONSTRAINT chat_members_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id) ON DELETE CASCADE;


--
-- Name: chats chats_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT chats_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.employees(id);


--
-- Name: drafts drafts_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drafts
    ADD CONSTRAINT drafts_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id) ON DELETE CASCADE;


--
-- Name: drafts drafts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drafts
    ADD CONSTRAINT drafts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.employees(id) ON DELETE CASCADE;


--
-- Name: employees employees_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.departments(id);


--
-- Name: employees employees_position_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_position_id_fkey FOREIGN KEY (position_id) REFERENCES public.positions(id);


--
-- Name: audit_log fk_audit_log_actor; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT fk_audit_log_actor FOREIGN KEY (actor_employee_id) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: audit_log fk_audit_log_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT fk_audit_log_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;


--
-- Name: chats fk_chats_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT fk_chats_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: companies fk_companies_owner_employee; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT fk_companies_owner_employee FOREIGN KEY (owner_employee_id, id) REFERENCES public.employees(id, company_id) DEFERRABLE INITIALLY DEFERRED NOT VALID;


--
-- Name: company_invitations fk_company_invitations_accepted_account_employee; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT fk_company_invitations_accepted_account_employee FOREIGN KEY (accepted_account_id, accepted_employee_id) REFERENCES public.accounts(id, employee_id) DEFERRABLE INITIALLY DEFERRED NOT VALID;


--
-- Name: company_invitations fk_company_invitations_accepted_employee; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT fk_company_invitations_accepted_employee FOREIGN KEY (accepted_employee_id, company_id) REFERENCES public.employees(id, company_id) DEFERRABLE INITIALLY DEFERRED NOT VALID;


--
-- Name: company_invitations fk_company_invitations_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT fk_company_invitations_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: company_invitations fk_company_invitations_invited_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT fk_company_invitations_invited_by FOREIGN KEY (invited_by, company_id) REFERENCES public.employees(id, company_id) ON DELETE RESTRICT;


--
-- Name: company_invitations fk_company_invitations_superseded_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_invitations
    ADD CONSTRAINT fk_company_invitations_superseded_by FOREIGN KEY (superseded_by_id) REFERENCES public.company_invitations(id) DEFERRABLE INITIALLY DEFERRED NOT VALID;


--
-- Name: company_membership_history fk_company_membership_history_changed_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_membership_history
    ADD CONSTRAINT fk_company_membership_history_changed_by FOREIGN KEY (changed_by) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: company_membership_history fk_company_membership_history_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_membership_history
    ADD CONSTRAINT fk_company_membership_history_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT;


--
-- Name: company_membership_history fk_company_membership_history_employee; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_membership_history
    ADD CONSTRAINT fk_company_membership_history_employee FOREIGN KEY (employee_id, company_id) REFERENCES public.employees(id, company_id) ON DELETE RESTRICT;


--
-- Name: company_membership_history fk_company_membership_history_invitation; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_membership_history
    ADD CONSTRAINT fk_company_membership_history_invitation FOREIGN KEY (source_invitation_id) REFERENCES public.company_invitations(id) ON DELETE SET NULL;


--
-- Name: employees fk_employees_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT fk_employees_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: idempotency_requests fk_idempotency_requests_invitation; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_requests
    ADD CONSTRAINT fk_idempotency_requests_invitation FOREIGN KEY (invitation_id) REFERENCES public.company_invitations(id) ON DELETE RESTRICT;


--
-- Name: idempotency_requests fk_idempotency_requests_principal; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.idempotency_requests
    ADD CONSTRAINT fk_idempotency_requests_principal FOREIGN KEY (principal_employee_id) REFERENCES public.employees(id) ON DELETE SET NULL;


--
-- Name: stickies fk_stickies_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT fk_stickies_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: task_statuses fk_task_statuses_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_statuses
    ADD CONSTRAINT fk_task_statuses_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: task_tags fk_task_tags_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags
    ADD CONSTRAINT fk_task_tags_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: task_tags_link fk_task_tags_link_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags_link
    ADD CONSTRAINT fk_task_tags_link_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: tasks fk_tasks_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT fk_tasks_company FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE RESTRICT NOT VALID;


--
-- Name: messages messages_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id) ON DELETE CASCADE;


--
-- Name: messages messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.employees(id);


--
-- Name: notifications notifications_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id);


--
-- Name: notifications notifications_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id);


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.employees(id);


--
-- Name: pinned_chats pinned_chats_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pinned_chats
    ADD CONSTRAINT pinned_chats_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id) ON DELETE CASCADE;


--
-- Name: pinned_chats pinned_chats_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pinned_chats
    ADD CONSTRAINT pinned_chats_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.employees(id) ON DELETE CASCADE;


--
-- Name: stickies stickies_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stickies
    ADD CONSTRAINT stickies_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.employees(id) ON DELETE CASCADE;


--
-- Name: task_comments task_comments_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comments
    ADD CONSTRAINT task_comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.employees(id);


--
-- Name: task_comments task_comments_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comments
    ADD CONSTRAINT task_comments_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE;


--
-- Name: task_files task_files_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_files
    ADD CONSTRAINT task_files_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE;


--
-- Name: task_files task_files_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_files
    ADD CONSTRAINT task_files_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.employees(id);


--
-- Name: task_observers task_observers_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_observers
    ADD CONSTRAINT task_observers_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(id);


--
-- Name: task_observers task_observers_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_observers
    ADD CONSTRAINT task_observers_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE;


--
-- Name: task_tags_link task_tags_link_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags_link
    ADD CONSTRAINT task_tags_link_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.task_tags(id);


--
-- Name: task_tags_link task_tags_link_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_tags_link
    ADD CONSTRAINT task_tags_link_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id) ON DELETE CASCADE;


--
-- Name: tasks tasks_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.employees(id);


--
-- Name: tasks tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.employees(id);


--
-- Name: tasks tasks_executor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_executor_id_fkey FOREIGN KEY (executor_id) REFERENCES public.employees(id);


--
-- Name: tasks tasks_priority_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_priority_id_fkey FOREIGN KEY (priority_id) REFERENCES public.task_priorities(id);


--
-- Name: tasks tasks_status_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_status_id_fkey FOREIGN KEY (status_id) REFERENCES public.task_statuses(id);


--
-- PostgreSQL database dump complete
--


