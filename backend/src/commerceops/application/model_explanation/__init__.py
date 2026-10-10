"""只读库存说明组件入口，业务/持久预算绑定由P203调用方负责。"""

from commerceops.application.model_explanation.contracts import ExplanationResult, ReferenceIds
from commerceops.application.model_explanation.service import ModelExplanationService

__all__ = ["ExplanationResult", "ModelExplanationService", "ReferenceIds"]
