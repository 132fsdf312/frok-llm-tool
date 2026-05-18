"""
Frok Code 配置管理
桌面版和移动版共用
"""

import json
from pathlib import Path


class ConfigManager:
    def __init__(self):
        self.config_dir = Path.home() / ".frok"
        self.config_file = self.config_dir / "config.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()

    def _load_config(self):
        """加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return self._default_config()

    def _default_config(self):
        """默认配置"""
        return {
            "providers": {
                "deepseek": {
                    "name": "DeepSeek",
                    "base_url": "https://api.deepseek.com",
                    "api_key": "",
                    "models": ["deepseek-v4-pro", "deepseek-chat", "deepseek-coder"],
                    "default_model": "deepseek-v4-pro"
                },
                "openai": {
                    "name": "OpenAI",
                    "base_url": "https://api.openai.com/v1",
                    "api_key": "",
                    "models": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
                    "default_model": "gpt-3.5-turbo"
                },
                "mimo": {
                    "name": "MiMo",
                    "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
                    "api_key": "",
                    "models": ["mimo-v2.5-pro", "mimo-v2-pro"],
                    "default_model": "mimo-v2.5-pro"
                },
                "aliyun": {
                    "name": "阿里云",
                    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "api_key": "",
                    "models": ["qwen-turbo", "qwen-plus", "qwen-max"],
                    "default_model": "qwen-turbo"
                }
            },
            "default_provider": "mimo",
            "max_tokens": 4096,
            "temperature": 0.7,
            "setup_complete": False
        }

    def save(self):
        """保存配置"""
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def get_provider(self, name=None):
        """获取提供商配置"""
        name = name or self.config["default_provider"]
        return self.config["providers"].get(name)

    def set_api_key(self, provider, key):
        """设置API Key"""
        if provider in self.config["providers"]:
            self.config["providers"][provider]["api_key"] = key
            self.save()

    def set_default_provider(self, provider):
        """设置默认提供商"""
        if provider in self.config["providers"]:
            self.config["default_provider"] = provider
            self.save()

    def add_provider(self, name, display_name, base_url, api_key="", models=None, default_model=""):
        """添加自定义提供商"""
        provider_id = name.lower().replace(" ", "_")
        self.config["providers"][provider_id] = {
            "name": display_name,
            "base_url": base_url,
            "api_key": api_key,
            "models": models or [],
            "default_model": default_model or (models[0] if models else "")
        }
        self.save()
        return provider_id

    def remove_provider(self, provider):
        """删除提供商"""
        if provider in self.config["providers"]:
            if provider == self.config["default_provider"]:
                return False, "不能删除默认提供商，请先切换默认提供商"
            del self.config["providers"][provider]
            self.save()
            return True, "删除成功"
        return False, "提供商不存在"

    def update_provider(self, provider, **kwargs):
        """更新提供商配置"""
        if provider in self.config["providers"]:
            for key, value in kwargs.items():
                if key in ["name", "base_url", "api_key", "models", "default_model"]:
                    self.config["providers"][provider][key] = value
            self.save()
            return True
        return False

    def add_model(self, provider, model_name):
        """添加模型"""
        if provider in self.config["providers"]:
            if model_name not in self.config["providers"][provider]["models"]:
                self.config["providers"][provider]["models"].append(model_name)
                self.save()
                return True
        return False

    def remove_model(self, provider, model_name):
        """删除模型"""
        if provider in self.config["providers"]:
            models = self.config["providers"][provider]["models"]
            if model_name in models:
                models.remove(model_name)
                if self.config["providers"][provider]["default_model"] == model_name:
                    self.config["providers"][provider]["default_model"] = models[0] if models else ""
                self.save()
                return True
        return False

    def is_setup_complete(self):
        """检查配置是否完成"""
        return self.config.get("setup_complete", False)

    def mark_setup_complete(self):
        """标记配置完成"""
        self.config["setup_complete"] = True
        self.save()
