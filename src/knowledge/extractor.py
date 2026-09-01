"""全文提取双射（需求 2c）。

与旧 ``arxiv_ingest.py`` 的关键区别：

- **整篇 ``flattened.tex`` 全文直接给 LLM**，不再正则切定理块、不再截 8000 字符。
- **要求 LLM 保留所有定义**（``symbol_definitions``），避免提取出的双射缺定义看不懂。
- **不设输出上限**（``chat_json`` 的 ``max_tokens=None``），避免长输出被 ``finish_reason=length`` 截断。

提取出的每条记录对齐第一层 ``data/bijection_records.json`` 的 schema，
可直接追加进第一层 json 双射库。
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.knowledge import ontology
from src.knowledge.llm import DEFAULT_MODEL, chat_json

logger = logging.getLogger(__name__)


class AlgorithmStep(BaseModel):
    step_number: int
    description: str
    operation_type: str = ""
    math_formula: str = ""


class SymbolDef(BaseModel):
    symbol: str
    meaning: str
    latex_def: str = ""


class ExtractedBijection(BaseModel):
    """LLM 对整篇论文提取出的单个双射（含完整定义）。"""

    source_object: str
    target_object: str
    source_object_name: str = ""   # 简短对象名（供 ontology 映射父/子节点）
    target_object_name: str = ""
    is_explicit: bool = True
    algorithm_steps: list[AlgorithmStep] = Field(default_factory=list)
    inverse_steps: list[AlgorithmStep] = Field(default_factory=list)
    cross_tags: list[str] = Field(default_factory=list)
    properties_preserved: list[str] = Field(default_factory=list)
    symbol_definitions: list[SymbolDef] = Field(default_factory=list)
    purpose: str = ""
    purpose_detail: str = ""
    confidence: float = 0.8

    @field_validator("is_explicit", mode="before")
    @classmethod
    def _bool_from_any(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return v

    @field_validator("algorithm_steps", "inverse_steps", "symbol_definitions", mode="before")
    @classmethod
    def _list_from_any(cls, v):
        return v if isinstance(v, list) else []


class BijectionExtractor:
    """对整篇论文调用 DeepSeek，提取全部双射（含完整定义，不截断）。"""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model = model

    def extract(self, paper_id: str, paper_title: str, authors: str,
                tex_text: str) -> list[dict]:
        """从整篇 tex 提取双射，返回对齐第一层 schema 的记录列表（含 primary_path）。"""
        data = chat_json(
            system=self._system_prompt(),
            user=self._user_prompt(paper_id, paper_title, authors, tex_text),
            model=self.model,
            temperature=0.2,
            max_tokens=None,  # 不设上限，避免截断
            retries=1,
        )
        records: list[dict] = []
        for item in data.get("bijections", []):
            try:
                ext = ExtractedBijection(**item)
            except Exception as exc:  # 单条字段容错失败，跳过该条
                logger.warning("[%s] 单条双射解析失败: %s", paper_id, exc)
                continue
            records.append(self._to_record(paper_id, paper_title, authors, ext))
        return records

    def _to_record(self, paper_id: str, paper_title: str, authors: str,
                   ext: ExtractedBijection) -> dict:
        """补全 paper 元数据与 ontology 路径，产出第一层 schema 记录。"""
        return {
            "paper_id": paper_id,
            "paper_title": paper_title,
            "authors": authors,
            "source_object": ext.source_object,
            "target_object": ext.target_object,
            "source_primary_path": ontology.find_path(ext.source_object_name),
            "target_primary_path": ontology.find_path(ext.target_object_name),
            "is_explicit": ext.is_explicit,
            "algorithm_steps": [s.model_dump() for s in ext.algorithm_steps],
            "inverse_steps": [s.model_dump() for s in ext.inverse_steps],
            "cross_tags": ext.cross_tags,
            "properties_preserved": ext.properties_preserved,
            "symbol_definitions": [s.model_dump() for s in ext.symbol_definitions],
            "purpose": ext.purpose,
            "purpose_detail": ext.purpose_detail,
            "confidence": ext.confidence,
            "verified": False,
        }

    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        tags = ", ".join(sorted(ontology.cross_tags()))
        parents = ", ".join(ontology.parents())
        return (
            "你是一名组合数学专家，任务是从一篇论文的完整 LaTeX 源码中，提取其中所有"
            "「双射 / 对合」构造，输出结构化 JSON。\n\n"
            "【最重要：保留完整定义】\n"
            "提取每个双射时，必须把涉及的所有符号、对象、统计量的定义一并写入 "
            "symbol_definitions（含 symbol / meaning / latex_def 三字段）。"
            "目标是读者只凭提取结果就能完全理解该双射，绝不能出现「拿到映射却缺定义看不懂」。\n\n"
            "【每个双射输出字段】\n"
            "- source_object / target_object：源/目标对象的论文原文描述（可含 LaTeX 宏）。\n"
            "- source_object_name / target_object_name：简短英文对象名（如 \"dyck path\"、"
            "\"binary tree\"、\"312-avoiding permutation\"），供对象本体映射，不要含 LaTeX。\n"
            "- is_explicit：是否显式给出可逆映射构造（对合/自逆映射也算 true）。\n"
            "- algorithm_steps：正映射步骤数组 [{step_number, description, operation_type, math_formula}]。\n"
            "- inverse_steps：逆映射步骤数组（同上）。\n"
            "- cross_tags：从以下标签中选（可多选，无则空数组）：\n"
            f"  {tags}\n"
            "- properties_preserved：该双射保持的统计量名（如 area、descents、number of parts）。\n"
            "- symbol_definitions：涉及的所有符号/对象/统计量定义 [{symbol, meaning, latex_def}]。\n"
            "- purpose：identity_proof / structural_correspondence / statistic_equidistribution / enumeration。\n"
            "- purpose_detail：一句话说明该双射的核心思想（中文）。\n"
            "- confidence：0~1 的置信度。\n\n"
            "【对象本体父节点清单（供 source/target_object_name 尽量归入其一）】\n"
            f"{parents}\n\n"
            "【输出】严格 JSON 对象：{\"bijections\": [<上述每个双射的字段>]}。"
            "若论文不含任何双射/对合，输出 {\"bijections\": []}。"
        )

    def _user_prompt(self, paper_id: str, paper_title: str, authors: str,
                     tex_text: str) -> str:
        return (
            f"论文 arXiv:{paper_id} — 标题: {paper_title} — 作者: {authors}\n\n"
            "以下是该论文的完整 LaTeX 源码（已展平 \\input/\\include）：\n\n"
            f"---\n{tex_text}\n---\n\n"
            "请提取其中所有双射/对合构造，输出 JSON（{\"bijections\": [...]}，"
            "每个双射含全部字段，符号定义务必完整）。"
        )
