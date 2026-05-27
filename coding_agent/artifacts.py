from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class StageStatus(Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


@dataclass
class UserRequirement:
    raw_text: str


@dataclass
class ProjectBrief:
    project_name: str
    background: str
    goal: str
    scope: str
    team: list[str]
    feasibility: str
    raw: str = ""


@dataclass
class Feature:
    id: str
    name: str
    description: str
    acceptance_criteria: list[str]


@dataclass
class FeatureList:
    overview: str
    features: list[Feature]
    raw: str = ""


@dataclass
class TechPlan:
    language: str
    framework: str
    architecture: str
    modules: list[dict]
    dev_phases: list[str]
    raw: str = ""


@dataclass
class APIEndpoint:
    method: str
    path: str
    description: str
    request_body: Optional[dict]
    response: dict


@dataclass
class DataModel:
    name: str
    fields: list[dict]


@dataclass
class APISpec:
    data_models: list[DataModel]
    endpoints: list[APIEndpoint]
    raw: str = ""


@dataclass
class UIPage:
    name: str
    route: str
    description: str
    components: list[str]
    api_calls: list[str]


@dataclass
class UISpec:
    pages: list[UIPage]
    shared_components: list[str]
    raw: str = ""


@dataclass
class CodeFile:
    path: str
    content: str
    description: str


@dataclass
class CodeOutput:
    files: list[CodeFile] = field(default_factory=list)
    raw: str = ""


@dataclass
class TestCase:
    feature_id: str
    feature_name: str
    status: str  # pass / fail
    detail: str


@dataclass
class TestReport:
    passed: int
    failed: int
    cases: list[TestCase]
    summary: str
    raw: str = ""


@dataclass
class AcceptanceResult:
    passed: bool
    verdict: str
    unmet_requirements: list[str]
    raw: str = ""


@dataclass
class PipelineState:
    requirement: Optional[UserRequirement] = None
    brief: Optional[ProjectBrief] = None
    features: Optional[FeatureList] = None
    tech_plan: Optional[TechPlan] = None
    api_spec: Optional[APISpec] = None
    ui_spec: Optional[UISpec] = None
    code_output: Optional[CodeOutput] = None
    test_report: Optional[TestReport] = None
    acceptance: Optional[AcceptanceResult] = None
