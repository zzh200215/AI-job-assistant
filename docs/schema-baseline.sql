-- 数据库 Schema 基线快照（T1-2 冻结数据模型基线）
-- 生成方式：backend/scripts/export_schema_baseline.py（离线编译，MySQL 8.0 方言）
-- 变更纪律：任何表结构变更必须先走 Alembic 迁移（backend/migrations/versions/），
--           再重新生成本快照并连同迁移脚本一并提交；CI 会对本文件做漂移检测。

CREATE INDEX ix_ai_release_created_at ON ai_release (created_at);
CREATE INDEX ix_ai_release_status ON ai_release (status);
CREATE INDEX ix_api_bill_api_key_id ON api_bill (api_key_id);
CREATE INDEX ix_api_bill_tenant_id ON api_bill (tenant_id);
CREATE INDEX ix_api_keys_tenant_id ON api_keys (tenant_id);
CREATE INDEX ix_api_usage_api_key_id ON api_usage (api_key_id);
CREATE INDEX ix_api_usage_created_at ON api_usage (created_at);
CREATE INDEX ix_api_usage_request_id ON api_usage (request_id);
CREATE INDEX ix_api_usage_tenant_id ON api_usage (tenant_id);
CREATE INDEX ix_audit_log_action ON audit_log (action);
CREATE INDEX ix_audit_log_created_at ON audit_log (created_at);
CREATE INDEX ix_audit_log_tenant_user ON audit_log (tenant_id, user_id);
CREATE INDEX ix_audit_log_user_id ON audit_log (user_id);
CREATE INDEX ix_embedding_usage_daily_model ON embedding_usage_daily (model);
CREATE INDEX ix_embedding_usage_daily_provider ON embedding_usage_daily (provider);
CREATE INDEX ix_embedding_usage_daily_stat_date ON embedding_usage_daily (stat_date);
CREATE INDEX ix_interview_question_bank_tenant_id ON interview_question_bank (tenant_id);
CREATE INDEX ix_interview_question_category ON interview_question (category);
CREATE INDEX ix_interview_question_difficulty ON interview_question (difficulty);
CREATE INDEX ix_interview_question_sub_category ON interview_question (sub_category);
CREATE INDEX ix_interview_report_template_tenant_id ON interview_report_template (tenant_id);
CREATE INDEX ix_interview_scoring_rule_tenant_id ON interview_scoring_rule (tenant_id);
CREATE INDEX ix_interview_session_jd_id ON interview_session (jd_id);
CREATE INDEX ix_interview_session_resume_id ON interview_session (resume_id);
CREATE INDEX ix_interview_session_status ON interview_session (status);
CREATE INDEX ix_interview_session_tenant_user ON interview_session (tenant_id, user_id);
CREATE INDEX ix_interview_session_user_id ON interview_session (user_id);
CREATE INDEX ix_interview_turn_evaluation_session_id ON interview_turn_evaluation (session_id);
CREATE INDEX ix_interview_turn_evaluation_status ON interview_turn_evaluation (status);
CREATE INDEX ix_jd_embedding_jd_id ON jd_embedding (jd_id);
CREATE INDEX ix_job_application_pipeline_company ON job_application_pipeline (company);
CREATE INDEX ix_job_application_pipeline_create_time ON job_application_pipeline (create_time);
CREATE INDEX ix_job_application_pipeline_jd_id ON job_application_pipeline (jd_id);
CREATE INDEX ix_job_application_pipeline_resume_id ON job_application_pipeline (resume_id);
CREATE INDEX ix_job_application_pipeline_resume_version_id ON job_application_pipeline (resume_version_id);
CREATE INDEX ix_job_application_pipeline_stage ON job_application_pipeline (stage);
CREATE INDEX ix_job_application_pipeline_target_id ON job_application_pipeline (target_id);
CREATE INDEX ix_job_application_pipeline_tenant_user ON job_application_pipeline (tenant_id, user_id);
CREATE INDEX ix_job_application_pipeline_title ON job_application_pipeline (title);
CREATE INDEX ix_job_application_pipeline_update_time ON job_application_pipeline (update_time);
CREATE INDEX ix_job_application_pipeline_user_id ON job_application_pipeline (user_id);
CREATE INDEX ix_job_bookmark_action ON job_bookmark (action);
CREATE INDEX ix_job_bookmark_jd_id ON job_bookmark (jd_id);
CREATE INDEX ix_job_bookmark_tenant_user ON job_bookmark (tenant_id, user_id);
CREATE INDEX ix_job_bookmark_user_id ON job_bookmark (user_id);
CREATE INDEX ix_job_journal_created_at ON job_journal (created_at);
CREATE INDEX ix_job_journal_entry_type ON job_journal (entry_type);
CREATE INDEX ix_job_journal_jd_id ON job_journal (jd_id);
CREATE INDEX ix_job_journal_pipeline_id ON job_journal (pipeline_id);
CREATE INDEX ix_job_journal_user_id ON job_journal (user_id);
CREATE INDEX ix_job_recommend_feedback_jd_id ON job_recommend_feedback (jd_id);
CREATE INDEX ix_job_recommend_feedback_resume_id ON job_recommend_feedback (resume_id);
CREATE INDEX ix_job_recommend_feedback_tenant_user ON job_recommend_feedback (tenant_id, user_id);
CREATE INDEX ix_job_recommend_feedback_user_id ON job_recommend_feedback (user_id);
CREATE INDEX ix_job_target_is_primary ON job_target (is_primary);
CREATE INDEX ix_job_target_status ON job_target (status);
CREATE INDEX ix_job_target_user_id ON job_target (user_id);
CREATE INDEX ix_kb_document_organization_id ON kb_document (organization_id);
CREATE INDEX ix_kb_document_tenant_id ON kb_document (tenant_id);
CREATE INDEX ix_kb_document_user_id ON kb_document (user_id);
CREATE INDEX ix_match_score_jd_id ON match_score (jd_id);
CREATE INDEX ix_match_score_resume_id ON match_score (resume_id);
CREATE INDEX ix_match_score_tenant_user ON match_score (tenant_id, user_id);
CREATE INDEX ix_match_score_user_id ON match_score (user_id);
CREATE INDEX ix_notification_created_at ON notification (created_at);
CREATE INDEX ix_notification_is_read ON notification (is_read);
CREATE INDEX ix_notification_type ON notification (type);
CREATE INDEX ix_notification_user_id ON notification (user_id);
CREATE INDEX ix_operational_alert_last_seen_at ON operational_alert (last_seen_at);
CREATE INDEX ix_operational_alert_resolved_at ON operational_alert (resolved_at);
CREATE INDEX ix_operational_alert_severity ON operational_alert (severity);
CREATE INDEX ix_operational_alert_status ON operational_alert (status);
CREATE INDEX ix_organization_expires_at ON organization (expires_at);
CREATE INDEX ix_organization_membership_organization_id ON organization_membership (organization_id);
CREATE INDEX ix_organization_membership_user_id ON organization_membership (user_id);
CREATE INDEX ix_organization_owner_id ON organization (owner_id);
CREATE INDEX ix_organization_plan_tier ON organization (plan_tier);
CREATE INDEX ix_organization_sso_identity_organization_id ON organization_sso_identity (organization_id);
CREATE INDEX ix_organization_sso_identity_user_id ON organization_sso_identity (user_id);
CREATE INDEX ix_organization_sso_state_expires_at ON organization_sso_state (expires_at);
CREATE INDEX ix_organization_sso_state_organization_id ON organization_sso_state (organization_id);
CREATE INDEX ix_organization_status ON organization (status);
CREATE INDEX ix_prompt_trace_analysis_record_id ON prompt_trace (analysis_record_id);
CREATE INDEX ix_prompt_trace_created_at ON prompt_trace (created_at);
CREATE INDEX ix_prompt_trace_feedback_label ON prompt_trace (feedback_label);
CREATE INDEX ix_prompt_trace_jd_id ON prompt_trace (jd_id);
CREATE INDEX ix_prompt_trace_prompt_family ON prompt_trace (prompt_family);
CREATE INDEX ix_prompt_trace_prompt_hash ON prompt_trace (prompt_hash);
CREATE INDEX ix_prompt_trace_prompt_name ON prompt_trace (prompt_name);
CREATE INDEX ix_prompt_trace_request_id ON prompt_trace (request_id);
CREATE INDEX ix_prompt_trace_response_source ON prompt_trace (response_source);
CREATE INDEX ix_prompt_trace_resume_id ON prompt_trace (resume_id);
CREATE INDEX ix_prompt_trace_source ON prompt_trace (source);
CREATE INDEX ix_prompt_trace_task_id ON prompt_trace (task_id);
CREATE INDEX ix_prompt_trace_user_id ON prompt_trace (user_id);
CREATE INDEX ix_resume_version_parent_version_id ON resume_version (parent_version_id);
CREATE INDEX ix_resume_version_resume_id ON resume_version (resume_id);
CREATE INDEX ix_resume_version_target_jd_id ON resume_version (target_jd_id);
CREATE INDEX ix_subscription_order_tenant_user ON subscription_order (tenant_id, user_id);
CREATE INDEX ix_subscription_order_user_id ON subscription_order (user_id);
CREATE INDEX ix_subscription_plan_tenant_id ON subscription_plan (tenant_id);
CREATE INDEX ix_tb_analysis_record_create_time ON tb_analysis_record (create_time);
CREATE INDEX ix_tb_analysis_record_jd_id ON tb_analysis_record (jd_id);
CREATE INDEX ix_tb_analysis_record_resume_id ON tb_analysis_record (resume_id);
CREATE INDEX ix_tb_analysis_record_tenant_user ON tb_analysis_record (tenant_id, user_id);
CREATE INDEX ix_tb_analysis_record_user_id ON tb_analysis_record (user_id);
CREATE INDEX ix_tb_jd_company ON tb_jd (company);
CREATE INDEX ix_tb_jd_create_time ON tb_jd (create_time);
CREATE INDEX ix_tb_jd_tenant_active ON tb_jd (tenant_id, is_active);
CREATE INDEX ix_tb_jd_title ON tb_jd (title);
CREATE INDEX ix_tb_jd_user_id ON tb_jd (user_id);
CREATE INDEX ix_tb_resume_create_time ON tb_resume (create_time);
CREATE INDEX ix_tb_resume_name ON tb_resume (name);
CREATE INDEX ix_tb_resume_tenant_user ON tb_resume (tenant_id, user_id);
CREATE INDEX ix_tb_resume_user_id ON tb_resume (user_id);
CREATE INDEX ix_tenant_configs_tenant_id ON tenant_configs (tenant_id);
CREATE INDEX ix_tenant_domain_bindings_tenant_id ON tenant_domain_bindings (tenant_id);
CREATE INDEX ix_user_subscription_tenant_user ON user_subscription (tenant_id, user_id);
CREATE INDEX ix_user_subscription_user_id ON user_subscription (user_id);
CREATE INDEX ix_webhook_subscriptions_api_key_id ON webhook_subscriptions (api_key_id);
CREATE INDEX ix_webhook_subscriptions_tenant_id ON webhook_subscriptions (tenant_id);
CREATE UNIQUE INDEX ix_ai_release_release_key ON ai_release (release_key);
CREATE UNIQUE INDEX ix_api_keys_key_hash ON api_keys (key_hash);
CREATE UNIQUE INDEX ix_api_pricing_endpoint ON api_pricing (endpoint);
CREATE UNIQUE INDEX ix_operational_alert_alert_key ON operational_alert (alert_key);
CREATE UNIQUE INDEX ix_organization_slug ON organization (slug);
CREATE UNIQUE INDEX ix_organization_sso_state_state_hash ON organization_sso_state (state_hash);
CREATE UNIQUE INDEX uq_interview_question_bank_tenant_type ON interview_question_bank (tenant_id, type);
CREATE UNIQUE INDEX uq_interview_report_template_tenant ON interview_report_template (tenant_id);
CREATE UNIQUE INDEX uq_interview_scoring_rule_tenant_dim ON interview_scoring_rule (tenant_id, dimension);
CREATE UNIQUE INDEX uq_match_score_resume_version_jd ON match_score (resume_id, resume_version, jd_id);
CREATE UNIQUE INDEX uq_subscription_plan_tenant_tier ON subscription_plan (tenant_id, tier);

CREATE TABLE agent_task (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	resume_id BIGINT NOT NULL, 
	jd_id BIGINT NOT NULL, 
	analysis_record_id BIGINT, 
	strategy_name VARCHAR(50), 
	retry_of_task_id BIGINT, 
	intent VARCHAR(100), 
	intent_detail JSON, 
	plan JSON, 
	final_report JSON, 
	status VARCHAR(20) NOT NULL, 
	error_msg TEXT, 
	start_time DATETIME, 
	end_time DATETIME, 
	create_time DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE agent_run (
	id BIGINT NOT NULL, 
	resume_id BIGINT NOT NULL, 
	jd_id BIGINT NOT NULL, 
	user_request TEXT, 
	intent VARCHAR(50), 
	selected_agents JSON, 
	dispatch_reason TEXT, 
	status VARCHAR(20) NOT NULL, 
	summary_report JSON, 
	error_msg TEXT, 
	start_time DATETIME, 
	end_time DATETIME, 
	create_time DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE ai_release (
	id BIGINT NOT NULL, 
	release_key VARCHAR(100) NOT NULL, 
	provider VARCHAR(30) NOT NULL, 
	model VARCHAR(120) NOT NULL, 
	prompt_versions JSON NOT NULL, 
	evaluation_reports JSON NOT NULL, 
	gate_result JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	notes TEXT, 
	created_by BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	approved_by BIGINT, 
	approved_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE api_bill (
	id BIGINT NOT NULL, 
	api_key_id BIGINT NOT NULL, 
	tenant_id BIGINT NOT NULL, 
	period_start DATETIME NOT NULL, 
	period_end DATETIME NOT NULL, 
	usage_count INTEGER NOT NULL, 
	total_amount NUMERIC(10, 2) NOT NULL, 
	line_items JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE api_keys (
	id BIGINT NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	key_hash VARCHAR(64) NOT NULL, 
	tenant_id BIGINT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	daily_quota INTEGER NOT NULL, 
	expires_at DATETIME, 
	last_used_at DATETIME, 
	created_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE api_pricing (
	id BIGINT NOT NULL, 
	endpoint VARCHAR(80) NOT NULL, 
	unit_price NUMERIC(10, 2) NOT NULL, 
	is_active INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE api_usage (
	id BIGINT NOT NULL, 
	api_key_id BIGINT NOT NULL, 
	tenant_id BIGINT NOT NULL, 
	endpoint VARCHAR(80) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	amount NUMERIC(10, 2) NOT NULL, 
	request_id VARCHAR(64) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE audit_log (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	username VARCHAR(50), 
	action VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(50), 
	resource_id VARCHAR(50), 
	detail JSON, 
	ip_address VARCHAR(50), 
	user_agent VARCHAR(500), 
	status VARCHAR(20), 
	created_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE embedding_usage_daily (
	id BIGINT NOT NULL, 
	stat_date DATE NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	model VARCHAR(100) NOT NULL, 
	total_calls INTEGER NOT NULL, 
	total_texts INTEGER NOT NULL, 
	cache_hits INTEGER NOT NULL, 
	cache_misses INTEGER NOT NULL, 
	network_batches INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_embedding_usage_daily UNIQUE (stat_date, provider, model)
)

;

CREATE TABLE tb_resume (
	id BIGINT NOT NULL, 
	user_id BIGINT, 
	file_name VARCHAR(255) NOT NULL, 
	file_path VARCHAR(500) NOT NULL, 
	file_type VARCHAR(20), 
	file_size BIGINT, 
	raw_text TEXT, 
	parsed_json JSON, 
	name VARCHAR(100), 
	phone VARCHAR(50), 
	email VARCHAR(200), 
	years_exp INTEGER, 
	create_time DATETIME, 
	update_time DATETIME, 
	is_deleted INTEGER, 
	deleted_at DATETIME, 
	optimized_content TEXT, 
	optimized_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE tb_jd (
	id BIGINT NOT NULL, 
	user_id BIGINT, 
	tenant_id BIGINT, 
	title VARCHAR(200) NOT NULL, 
	company VARCHAR(200), 
	location VARCHAR(100), 
	salary_range VARCHAR(100), 
	raw_text TEXT NOT NULL, 
	parsed_json JSON, 
	source VARCHAR(20), 
	industry VARCHAR(100), 
	is_active INTEGER, 
	external_url VARCHAR(500), 
	external_id VARCHAR(100), 
	skill_tags JSON, 
	education_requirement VARCHAR(50), 
	experience_requirement VARCHAR(50), 
	create_time DATETIME, 
	update_time DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE interview_question_bank (
	id BIGINT NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	title VARCHAR(100), 
	prompt_template TEXT, 
	questions JSON, 
	tags JSON, 
	tenant_id BIGINT, 
	is_active INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE interview_scoring_rule (
	id BIGINT NOT NULL, 
	dimension VARCHAR(30) NOT NULL, 
	label VARCHAR(50), 
	weight NUMERIC(5, 4), 
	tenant_id BIGINT, 
	is_active INTEGER, 
	sort_order INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE interview_report_template (
	id BIGINT NOT NULL, 
	template TEXT NOT NULL, 
	tenant_id BIGINT, 
	is_active INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE interview_question (
	id BIGINT NOT NULL, 
	category VARCHAR(30) NOT NULL, 
	sub_category VARCHAR(50), 
	difficulty VARCHAR(10), 
	question TEXT NOT NULL, 
	intent VARCHAR(500), 
	ref_answer TEXT, 
	keywords JSON, 
	tags JSON, 
	source VARCHAR(50), 
	use_count INTEGER, 
	avg_score INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE job_journal (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	pipeline_id BIGINT, 
	jd_id BIGINT, 
	entry_type VARCHAR(20) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	content TEXT, 
	tags JSON, 
	mood VARCHAR(20), 
	rating INTEGER, 
	interview_role VARCHAR(100), 
	interview_round INTEGER, 
	interview_format VARCHAR(20), 
	attachments JSON, 
	is_private INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE job_target (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	position VARCHAR(100), 
	industry VARCHAR(50), 
	cities JSON, 
	salary_min INTEGER, 
	salary_max INTEGER, 
	skills JSON, 
	priority VARCHAR(10), 
	status VARCHAR(15), 
	is_primary INTEGER, 
	notes TEXT, 
	config JSON, 
	application_count INTEGER, 
	interview_count INTEGER, 
	offer_count INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE kb_document (
	id BIGINT NOT NULL, 
	user_id BIGINT, 
	organization_id BIGINT, 
	tenant_id BIGINT, 
	title VARCHAR(255) NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	file_type VARCHAR(20) NOT NULL, 
	file_size BIGINT, 
	file_path VARCHAR(500) NOT NULL, 
	doc_type VARCHAR(50) NOT NULL, 
	chunk_count INTEGER, 
	status VARCHAR(20) NOT NULL, 
	error_msg TEXT, 
	create_time DATETIME, 
	update_time DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE notification (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	type VARCHAR(30) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	content TEXT, 
	link VARCHAR(500), 
	ext_data JSON, 
	is_read INTEGER, 
	read_at DATETIME, 
	created_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE operational_alert (
	id BIGINT NOT NULL, 
	alert_key VARCHAR(100) NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	context JSON, 
	occurrences INTEGER NOT NULL, 
	first_seen_at DATETIME NOT NULL, 
	last_seen_at DATETIME NOT NULL, 
	acknowledged_at DATETIME, 
	acknowledged_by BIGINT, 
	resolved_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE organization (
	id BIGINT NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	slug VARCHAR(80) NOT NULL, 
	owner_id BIGINT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	sso_provider VARCHAR(20), 
	industry VARCHAR(50), 
	logo_url VARCHAR(500), 
	primary_color VARCHAR(20), 
	plan_tier VARCHAR(20) DEFAULT 'free' NOT NULL, 
	admin_user_id BIGINT, 
	expires_at DATETIME, 
	isolation_mode VARCHAR(20) DEFAULT 'shared' NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE organization_membership (
	id BIGINT NOT NULL, 
	organization_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	joined_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_organization_membership_user UNIQUE (organization_id, user_id)
)

;

CREATE TABLE organization_sso_identity (
	id BIGINT NOT NULL, 
	organization_id BIGINT NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	user_id BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_organization_sso_subject UNIQUE (organization_id, provider, subject)
)

;

CREATE TABLE organization_sso_state (
	id BIGINT NOT NULL, 
	state_hash VARCHAR(64) NOT NULL, 
	organization_id BIGINT NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	expires_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE subscription_plan (
	id BIGINT NOT NULL, 
	tier VARCHAR(20) NOT NULL, 
	tenant_id BIGINT, 
	is_custom INTEGER, 
	name VARCHAR(50) NOT NULL, 
	price_monthly NUMERIC(10, 2), 
	price_yearly NUMERIC(10, 2), 
	features JSON, 
	sort_order INTEGER, 
	is_active INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (id)
)

;

CREATE TABLE tenant_configs (
	id BIGINT NOT NULL, 
	tenant_id BIGINT NOT NULL, 
	config_key VARCHAR(50) NOT NULL, 
	config_value JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tenant_configs_key UNIQUE (tenant_id, config_key)
)

;

CREATE TABLE tenant_domain_bindings (
	id BIGINT NOT NULL, 
	tenant_id BIGINT NOT NULL, 
	domain VARCHAR(255) NOT NULL, 
	is_primary INTEGER DEFAULT '0' NOT NULL, 
	status VARCHAR(20) DEFAULT 'active' NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tenant_domain UNIQUE (domain)
)

;

CREATE TABLE tb_user (
	id BIGINT NOT NULL, 
	username VARCHAR(50) NOT NULL, 
	password VARCHAR(255) NOT NULL, 
	email VARCHAR(100), 
	role VARCHAR(20) DEFAULT 'candidate' NOT NULL, 
	avatar_url VARCHAR(500), 
	nickname VARCHAR(50), 
	phone VARCHAR(20), 
	bio TEXT, 
	job_seeking_status VARCHAR(20), 
	expected_position VARCHAR(200), 
	expected_city VARCHAR(200), 
	expected_salary_min INTEGER, 
	expected_salary_max INTEGER, 
	expected_industry VARCHAR(200), 
	work_years INTEGER, 
	education VARCHAR(20), 
	current_employer VARCHAR(200), 
	current_position VARCHAR(200), 
	skill_tags JSON, 
	social_links JSON, 
	default_resume_id BIGINT, 
	default_target_id BIGINT, 
	notification_preferences JSON, 
	privacy_settings JSON, 
	language VARCHAR(10), 
	theme VARCHAR(10), 
	email_verified INTEGER, 
	active_organization_id BIGINT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (username), 
	UNIQUE (email)
)

;

CREATE TABLE webhook_subscriptions (
	id BIGINT NOT NULL, 
	api_key_id BIGINT NOT NULL, 
	tenant_id BIGINT NOT NULL, 
	event VARCHAR(80) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	secret VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE agent_step_log (
	id BIGINT NOT NULL, 
	task_id BIGINT NOT NULL, 
	step_name VARCHAR(100) NOT NULL, 
	step_index INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	input_data JSON, 
	output_data JSON, 
	started_at DATETIME, 
	completed_at DATETIME, 
	duration_ms INTEGER, 
	error_msg TEXT, 
	retry_count INTEGER, 
	create_time DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES agent_task (id) ON DELETE CASCADE
)

;

CREATE TABLE retrieval_log (
	id BIGINT NOT NULL, 
	task_id BIGINT NOT NULL, 
	step_log_id BIGINT, 
	query_text TEXT NOT NULL, 
	doc_type_filter VARCHAR(50), 
	top_k INTEGER, 
	result_count INTEGER, 
	results JSON, 
	duration_ms INTEGER, 
	create_time DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES agent_task (id) ON DELETE CASCADE
)

;

CREATE TABLE self_check_log (
	id BIGINT NOT NULL, 
	task_id BIGINT NOT NULL, 
	check_target VARCHAR(100), 
	passed SMALLINT, 
	score FLOAT, 
	issues JSON, 
	improvement JSON, 
	retry_needed SMALLINT, 
	create_time DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES agent_task (id) ON DELETE CASCADE
)

;

CREATE TABLE agent_message (
	id BIGINT NOT NULL, 
	run_id BIGINT NOT NULL, 
	agent_name VARCHAR(50) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	depends_on JSON, 
	input_data JSON, 
	output_data JSON, 
	error_msg TEXT, 
	started_at DATETIME, 
	completed_at DATETIME, 
	duration_ms INTEGER, 
	tokens_used INTEGER, 
	cost_cents FLOAT, 
	create_time DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES agent_run (id) ON DELETE CASCADE
)

;

CREATE TABLE agent_result (
	id BIGINT NOT NULL, 
	run_id BIGINT NOT NULL, 
	message_id BIGINT, 
	agent_name VARCHAR(50) NOT NULL, 
	result_type VARCHAR(50) NOT NULL, 
	result_json JSON NOT NULL, 
	summary VARCHAR(500), 
	create_time DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(run_id) REFERENCES agent_run (id) ON DELETE CASCADE
)

;

CREATE TABLE tb_analysis_record (
	id BIGINT NOT NULL, 
	user_id BIGINT, 
	resume_id BIGINT NOT NULL, 
	jd_id BIGINT NOT NULL, 
	match_score INTEGER, 
	match_report JSON, 
	optimize_suggestions JSON, 
	interview_questions JSON, 
	remark VARCHAR(500), 
	create_time DATETIME, 
	is_deleted INTEGER, 
	deleted_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE CASCADE
)

;

CREATE TABLE resume_version (
	id BIGINT NOT NULL, 
	resume_id BIGINT NOT NULL, 
	version_type VARCHAR(20) NOT NULL, 
	content TEXT NOT NULL, 
	format VARCHAR(10), 
	label VARCHAR(120), 
	target_jd_id BIGINT, 
	parent_version_id BIGINT, 
	change_log JSON, 
	suggestion_decisions JSON, 
	ats_snapshot JSON, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE CASCADE
)

;

CREATE TABLE interview_session (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	resume_id BIGINT, 
	jd_id BIGINT, 
	interview_type VARCHAR(20), 
	status VARCHAR(20), 
	questions JSON, 
	messages JSON, 
	evaluation JSON, 
	evaluation_status VARCHAR(20), 
	memory_snapshot JSON, 
	total_questions INTEGER, 
	answered_count INTEGER, 
	timeout_count INTEGER, 
	created_at DATETIME, 
	updated_at DATETIME, 
	completed_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE SET NULL, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE SET NULL
)

;

CREATE TABLE job_application_pipeline (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	resume_id BIGINT, 
	resume_version_id BIGINT, 
	resume_version_label VARCHAR(120), 
	feedback_type VARCHAR(30), 
	feedback_score INTEGER, 
	feedback_tags JSON, 
	feedback_note TEXT, 
	feedback_at DATETIME, 
	jd_id BIGINT, 
	target_id BIGINT, 
	title VARCHAR(200) NOT NULL, 
	company VARCHAR(200), 
	location VARCHAR(100), 
	salary_range VARCHAR(100), 
	source VARCHAR(20), 
	source_url VARCHAR(500), 
	summary TEXT, 
	raw_text TEXT, 
	experience_requirement VARCHAR(50), 
	education_requirement VARCHAR(50), 
	industry VARCHAR(100), 
	skill_tags JSON, 
	priority_score INTEGER, 
	priority_label VARCHAR(50), 
	stage VARCHAR(20) NOT NULL, 
	note TEXT, 
	next_action VARCHAR(255), 
	follow_up_at DATETIME, 
	resume_name VARCHAR(255), 
	stage_history JSON, 
	interview_at DATETIME, 
	interview_type VARCHAR(20), 
	interview_round INTEGER, 
	interview_location VARCHAR(255), 
	interview_contact VARCHAR(100), 
	offer_salary VARCHAR(100), 
	offer_details JSON, 
	offer_deadline DATETIME, 
	create_time DATETIME, 
	update_time DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE SET NULL, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE SET NULL, 
	FOREIGN KEY(target_id) REFERENCES job_target (id) ON DELETE SET NULL
)

;

CREATE TABLE job_recommend_feedback (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	resume_id BIGINT NOT NULL, 
	jd_id BIGINT NOT NULL, 
	feedback_type VARCHAR(10) NOT NULL, 
	match_score FLOAT, 
	created_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE CASCADE
)

;

CREATE TABLE job_bookmark (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	jd_id BIGINT NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	note VARCHAR(500), 
	created_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE CASCADE
)

;

CREATE TABLE jd_embedding (
	id BIGINT NOT NULL, 
	jd_id BIGINT NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	model VARCHAR(64) NOT NULL, 
	text_hash VARCHAR(32) NOT NULL, 
	dimension INTEGER NOT NULL, 
	vector TEXT NOT NULL, 
	create_time DATETIME, 
	update_time DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_jd_embedding_jd_provider_model UNIQUE (jd_id, provider, model), 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE CASCADE
)

;

CREATE TABLE match_score (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	resume_id BIGINT NOT NULL, 
	resume_version VARCHAR(64) NOT NULL, 
	jd_id BIGINT NOT NULL, 
	score FLOAT NOT NULL, 
	raw_score FLOAT NOT NULL, 
	cap_applied FLOAT, 
	method VARCHAR(32) NOT NULL, 
	dimensions_json TEXT, 
	skill_gap_json TEXT, 
	created_at DATETIME, 
	updated_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id) ON DELETE CASCADE, 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE CASCADE, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE CASCADE
)

;

CREATE TABLE user_subscription (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	plan_tier VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	start_at DATETIME NOT NULL, 
	end_at DATETIME, 
	auto_renew INTEGER, 
	quota_usage JSON, 
	quota_reset_at DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id)
)

;

CREATE TABLE subscription_order (
	id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	plan_tier VARCHAR(20) NOT NULL, 
	amount NUMERIC(10, 2), 
	currency VARCHAR(10), 
	status VARCHAR(20) NOT NULL, 
	payment_method VARCHAR(50), 
	payment_channel VARCHAR(50), 
	transaction_id VARCHAR(200), 
	period_start DATETIME, 
	period_end DATETIME, 
	idempotency_key VARCHAR(100), 
	created_at DATETIME, 
	paid_at DATETIME, 
	tenant_id BIGINT DEFAULT '1' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES tb_user (id), 
	UNIQUE (idempotency_key)
)

;

CREATE TABLE interview_turn_evaluation (
	id BIGINT NOT NULL, 
	session_id BIGINT NOT NULL, 
	turn_id VARCHAR(80) NOT NULL, 
	question_index INTEGER NOT NULL, 
	question TEXT NOT NULL, 
	category VARCHAR(50), 
	user_answer TEXT, 
	is_follow_up INTEGER, 
	status VARCHAR(20) NOT NULL, 
	completeness INTEGER, 
	accuracy INTEGER, 
	depth INTEGER, 
	expression INTEGER, 
	overall_score INTEGER, 
	feedback TEXT, 
	improvement TEXT, 
	evidence JSON, 
	error_msg VARCHAR(500), 
	created_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_interview_turn_evaluation_turn UNIQUE (session_id, turn_id), 
	FOREIGN KEY(session_id) REFERENCES interview_session (id) ON DELETE CASCADE
)

;

CREATE TABLE prompt_trace (
	id BIGINT NOT NULL, 
	request_id VARCHAR(100), 
	source VARCHAR(120), 
	prompt_version VARCHAR(50), 
	prompt_family VARCHAR(50), 
	prompt_name VARCHAR(100), 
	provider VARCHAR(20) NOT NULL, 
	model VARCHAR(100), 
	response_source VARCHAR(20) NOT NULL, 
	degraded SMALLINT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	cache_hit SMALLINT NOT NULL, 
	duration_ms INTEGER, 
	prompt_chars INTEGER, 
	prompt_hash VARCHAR(32), 
	prompt_text TEXT, 
	response_text TEXT, 
	response_json JSON, 
	error_message TEXT, 
	trace_context JSON, 
	prompt_metadata JSON, 
	feedback_label VARCHAR(50), 
	feedback_note TEXT, 
	feedback_score FLOAT, 
	prompt_tokens INTEGER NOT NULL, 
	completion_tokens INTEGER NOT NULL, 
	total_tokens INTEGER NOT NULL, 
	cost_cents FLOAT NOT NULL, 
	task_id BIGINT, 
	analysis_record_id BIGINT, 
	user_id BIGINT, 
	resume_id BIGINT, 
	jd_id BIGINT, 
	created_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES agent_task (id) ON DELETE SET NULL, 
	FOREIGN KEY(analysis_record_id) REFERENCES tb_analysis_record (id) ON DELETE SET NULL, 
	FOREIGN KEY(user_id) REFERENCES tb_user (id) ON DELETE SET NULL, 
	FOREIGN KEY(resume_id) REFERENCES tb_resume (id) ON DELETE SET NULL, 
	FOREIGN KEY(jd_id) REFERENCES tb_jd (id) ON DELETE SET NULL
)

;
