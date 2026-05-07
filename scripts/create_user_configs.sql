-- Supabase SQL: user_configs テーブルの作成
-- Supabase SQL Editor で実行してください

CREATE TABLE IF NOT EXISTS user_configs (
    line_user_id TEXT PRIMARY KEY,
    persona_type TEXT NOT NULL DEFAULT 'friendly',
    brevity_level TEXT NOT NULL DEFAULT 'short',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 更新時に updated_at を自動更新するトリガー（任意）
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_user_configs_updated_at ON user_configs;
CREATE TRIGGER trigger_user_configs_updated_at
    BEFORE UPDATE ON user_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
