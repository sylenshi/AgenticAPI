"""Skill 加载器：内置运维 SOP + 管理员自定义技能池

形态（采纳 pi 的"目录 + 按需加载"模式）：system prompt 只注入一行一条的目录，
全文由 load_skill 工具按需读取，控制每轮固定 token 开销。

存放两处合并加载：
- 内置：app/agent_skills/*.md（随代码部署，物理上不可能被运行时写入覆盖）；
- 自定义：backend/data/agent_skills/*.md（save_skill 写入，同名覆盖更新）。

安全约束（防"注入持久化"——模型生成内容落盘后持续影响后续所有会话）：
1. name 强制 slug 校验（^[a-z0-9][a-z0-9-]{1,63}$），防路径穿越，仅可写单目录；
2. 单文件 ≤ 32KB；content 落盘前过 redact_text 兜底清除残留密钥；
3. 删除仅限自定义目录，内置 skill 不可删。
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.config import DATA_DIR
from app.services.agent.redact import redact_text

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "agent_skills"
CUSTOM_SKILLS_DIR = DATA_DIR / "agent_skills"

# slug 校验：小写字母/数字开头，允许连字符，总长 2-64（防路径穿越与大写/中文文件名）
SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SKILL_MAX_BYTES = 32 * 1024


@dataclass
class SkillMeta:
    name: str
    description: str
    triggers: str
    source: str  # builtin / custom
    update_time: str


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 frontmatter（--- 包裹的 name/description/triggers）+ 正文；无 frontmatter 时宽容降级"""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
            body = parts[2].lstrip("\n")
    return meta, body


def _load_dir(directory: Path, source: str) -> dict[str, SkillMeta]:
    """读取一个 skill 目录的全部条目（目录不存在返回空）"""
    skills: dict[str, SkillMeta] = {}
    if not directory.exists():
        return skills
    for path in sorted(directory.glob("*.md")):
        if not SKILL_NAME_RE.match(path.stem):
            continue  # 命名不合规的文件不入目录（历史脏文件防御）
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, _ = _parse_frontmatter(text)
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        skills[path.stem] = SkillMeta(
            name=path.stem,
            description=meta.get("description", ""),
            triggers=meta.get("triggers", ""),
            source=source,
            update_time=mtime,
        )
    return skills


def list_skills() -> list[SkillMeta]:
    """全量技能池目录（自定义同名覆盖内置）"""
    merged = _load_dir(BUILTIN_SKILLS_DIR, "builtin")
    merged.update(_load_dir(CUSTOM_SKILLS_DIR, "custom"))
    return sorted(merged.values(), key=lambda s: s.name)


def catalog_text() -> str:
    """system prompt 用的目录文本：每条一行（名称 + 一句描述 + 来源）"""
    lines = ["<available_skills>"]
    for skill in list_skills():
        tag = f"（{skill.triggers}）" if skill.triggers else ""
        lines.append(f"- {skill.name}: {skill.description}{tag} [{skill.source}]")
    lines.append("需要时用 load_skill 工具读取全文，按其中的 SOP 执行；偏离流程要说明理由。")
    lines.append("</available_skills>")
    return "\n".join(lines)


def load_skill(name: str) -> str | None:
    """读取 skill 全文（自定义优先），不存在返回 None"""
    if not SKILL_NAME_RE.match(name or ""):
        return None
    for directory in (CUSTOM_SKILLS_DIR, BUILTIN_SKILLS_DIR):
        path = directory / f"{name}.md"
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def save_skill(*, name: str, description: str, triggers: str, content: str,
               extra_secrets: list[str] | None = None) -> Path:
    """
    保存（新增/覆盖）自定义 skill，返回落盘路径。

    安全校验在落盘前完成：slug 合法、大小 ≤32KB、content 过脱敏兜底。
    抛 ValueError 表示校验失败（调用方包装为工具错误回传模型）。
    """
    if not SKILL_NAME_RE.match(name or ""):
        raise ValueError(
            f"skill 名称不合法：{name!r}。要求小写字母/数字开头，仅含小写字母、数字、连字符，长度 2-64"
        )
    description = (description or "").strip()
    if not description:
        raise ValueError("description 不能为空（目录展示与触发匹配都依赖它）")
    sanitized = redact_text(content or "", extra_secrets)
    if not sanitized.strip():
        raise ValueError("content 不能为空")

    frontmatter = "---\n"
    frontmatter += f"name: {name}\n"
    frontmatter += f"description: {description.replace(chr(10), ' ')}\n"
    if triggers and triggers.strip():
        frontmatter += f"triggers: {triggers.strip().replace(chr(10), ' ')}\n"
    frontmatter += "---\n\n"
    blob = (frontmatter + sanitized).encode("utf-8")
    if len(blob) > SKILL_MAX_BYTES:
        raise ValueError(f"skill 内容超过 32KB 上限（当前 {len(blob)} 字节），请精简后重试")

    CUSTOM_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    path = CUSTOM_SKILLS_DIR / f"{name}.md"
    path.write_text(frontmatter + sanitized, encoding="utf-8")
    return path


def delete_skill(name: str) -> bool:
    """删除自定义 skill；内置 skill（自定义目录无此文件）不可删，返回 False"""
    if not SKILL_NAME_RE.match(name or ""):
        raise ValueError(f"skill 名称不合法：{name!r}")
    path = CUSTOM_SKILLS_DIR / f"{name}.md"
    if not path.is_file():
        return False
    path.unlink()
    return True
