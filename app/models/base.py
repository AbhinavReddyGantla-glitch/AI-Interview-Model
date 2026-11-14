# Import all the models here so that Alembic can detect them
from app.database.base_class import Base  # noqa
from app.models.candidate import Candidate  # noqa
from app.models.question import QuestionBank  # noqa
from app.models.session import InterviewSession, SessionQuestion  # noqa
from app.models.answer import CandidateAnswer  # noqa
from app.models.score import InterviewScore  # noqa
from app.models.cache import InterviewTemplateCache  # noqa
from app.models.report import EvaluationReport  # noqa
from app.models.resume import Resume  # noqa
