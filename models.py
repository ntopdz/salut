#!/usr/bin/env python3
"""
models.py: يحتوي على تعريفات نماذج قاعدة البيانات باستخدام SQLAlchemy لنظام Reordering Sync Quantum Enhanced.
"""

import logging
from sqlalchemy import create_engine, Column, Integer, String, Date, Float, Boolean, ForeignKey, Index, Text, DateTime, or_, CheckConstraint
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import text

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ReorderingSyncQuantumEnhanced")

# قاعدة البيانات SQLite
DATABASE_URL = "sqlite:///reordering_sync_quantum_enhanced.db"
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# تعريف الجداول مع قيود تفصيلية
class ReorderingTable(Base):
    __tablename__ = "reordering_table"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False, CheckConstraint("year >= 1900 AND year <= 2100"))
    name = Column(String(200), nullable=False)
    total_seniority_days = Column(Integer, nullable=False, CheckConstraint("total_seniority_days >= 0"))
    approved_seniority_days = Column(Integer, nullable=False, CheckConstraint("approved_seniority_days >= 0"))
    suspension_days = Column(Integer, default=0, CheckConstraint("suspension_days >= 0"))
    southern_seniority_days = Column(Integer, default=0, CheckConstraint("southern_seniority_days >= 0"))
    southern_seniority_exhausted = Column(Boolean, default=False)
    points = Column(Float, default=0.0, CheckConstraint("points >= 0"))
    current_grade = Column(Integer, nullable=False, CheckConstraint("current_grade >= 0"))
    current_indice = Column(Integer, nullable=False, CheckConstraint("current_indice >= 0"))
    new_grade = Column(Integer, nullable=False, CheckConstraint("new_grade >= 0"))
    new_indice = Column(Integer, nullable=False, CheckConstraint("new_indice >= 0"))
    rank_indice = Column(Integer, nullable=False, CheckConstraint("rank_indice >= 0"))
    promotion_type = Column(String(20), nullable=False)
    effective_date = Column(Date, nullable=False, index=True)
    new_effective_date = Column(Date, nullable=False, index=True)
    financial_effect_date = Column(Date, nullable=False)
    remaining_seniority = Column(Integer, default=0, CheckConstraint("remaining_seniority >= 0"))
    experience_years = Column(Float, default=0.0, CheckConstraint("experience_years >= 0"))
    suspension_impact = Column(Float, default=0.0, CheckConstraint("suspension_impact >= 0"))
    custom_text1 = Column(String(200), default="")
    custom_text2 = Column(String(200), default="")
    custom_date1 = Column(Date)
    custom_date2 = Column(Date)
    notes = Column(String(500))
    __table_args__ = (
        Index('idx_reordering_employee_year', 'employee_id', 'year', unique=True),
    )
    employee = relationship("Employee", back_populates="reorderings")

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    birth_date = Column(Date, nullable=False, index=True)
    hire_date = Column(Date, nullable=False, index=True)
    region_type = Column(Integer, default=0, CheckConstraint("region_type IN (0, 1, 2, 3, 4)"))
    gender = Column(String(10), default="غير محدد", CheckConstraint("gender IN ('ذكر', 'أنثى', 'غير محدد')"))
    marital_status = Column(String(20), default="غير محدد", CheckConstraint("marital_status IN ('أعزب', 'متزوج', 'غير محدد')"))
    current_indice = Column(Integer, default=0, CheckConstraint("current_indice >= 0"))
    last_degree = Column(Integer, default=0, CheckConstraint("last_degree >= 0"))
    rank_id = Column(Integer, ForeignKey("ranks.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False, index=True)
    sectorial_institution_group_id = Column(Integer, ForeignKey("sectorial_institution_groups.id", ondelete="SET NULL", onupdate="CASCADE"), index=True)
    workplace_id = Column(Integer, ForeignKey("workplaces.id", ondelete="SET NULL", onupdate="CASCADE"), index=True)
    __table_args__ = (
        Index('idx_employee_name_birth', 'first_name', 'last_name', 'birth_date', unique=True),
    )
    reorderings = relationship("ReorderingTable", back_populates="employee", cascade="all, delete-orphan")
    promotions = relationship("Promotion", back_populates="employee", cascade="all, delete-orphan")
    evaluations = relationship("Evaluation", back_populates="employee", cascade="all, delete-orphan")
    professional_experience = relationship("ProfessionalExperience", back_populates="employee", cascade="all, delete-orphan")
    southern_seniority = relationship("SouthernSeniority", back_populates="employee", cascade="all, delete-orphan")
    suspensions = relationship("Suspension", back_populates="employee", cascade="all, delete-orphan")
    rank_history = relationship("EmployeeRankHistory", back_populates="employee", cascade="all, delete-orphan")

class Rank(Base):
    __tablename__ = "ranks"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(Integer, nullable=False, CheckConstraint("category >= 0"))
    corps_type = Column(String(50), nullable=False, default="مشتركة")
    base_indice = Column(Integer, nullable=False, default=100, CheckConstraint("base_indice >= 0"))
    __table_args__ = (
        Index('idx_rank_category', 'category', 'name'),
    )

class SectorialInstitutionGroup(Base):
    __tablename__ = "sectorial_institution_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    region = Column(Integer, nullable=False, CheckConstraint("region IN (0, 1, 2, 3, 4)"))
    __table_args__ = (
        Index('idx_institution_region', 'region', 'name', unique=True),
    )
    employees = relationship("Employee")

class Workplace(Base):
    __tablename__ = "workplaces"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    __table_args__ = (
        Index('idx_workplace_name', 'name', unique=True),
    )
    employees = relationship("Employee")

class Promotion(Base):
    __tablename__ = "promotions"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    promotion_date = Column(Date, nullable=False, index=True)
    effective_date = Column(Date, nullable=False, index=True)
    from_grade = Column(Integer, nullable=False, CheckConstraint("from_grade >= 0"))
    to_grade = Column(Integer, nullable=False, CheckConstraint("to_grade >= 0"))
    promotion_type = Column(String(20), nullable=False)
    points = Column(Float, default=0.0, CheckConstraint("points >= 0"))
    indice = Column(Integer, nullable=False, CheckConstraint("indice >= 0"))
    __table_args__ = (
        Index('idx_promotion_employee_date', 'employee_id', 'promotion_date', unique=True),
    )
    employee = relationship("Employee", back_populates="promotions")

class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    evaluation_year = Column(Integer, nullable=False, index=True, CheckConstraint("evaluation_year >= 1900 AND evaluation_year <= 2100"))
    annual_points = Column(Float, nullable=False, default=0.0, CheckConstraint("annual_points >= 0"))
    __table_args__ = (
        Index('idx_evaluation_employee_year', 'employee_id', 'evaluation_year', unique=True),
    )
    employee = relationship("Employee", back_populates="evaluations")

class ProfessionalExperience(Base):
    __tablename__ = "professional_experience"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    months = Column(Integer, nullable=False, CheckConstraint("months >= 0"))
    qualification_match = Column(Boolean, nullable=False, default=False)
    same_rank = Column(Boolean, nullable=False, default=False)
    applied = Column(Boolean, default=False)
    __table_args__ = (
        Index('idx_prof_exp_employee_period', 'employee_id', 'start_date', 'end_date', unique=True),
        CheckConstraint("end_date >= start_date"),
    )
    employee = relationship("Employee", back_populates="professional_experience")

class SouthernSeniority(Base):
    __tablename__ = "southern_seniority"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    region_type = Column(Integer, nullable=False, CheckConstraint("region_type IN (0, 1, 2, 3, 4)"))
    additional_months = Column(Integer, nullable=False, default=0, CheckConstraint("additional_months >= 0"))
    exhausted = Column(Boolean, default=False)
    __table_args__ = (
        Index('idx_southern_employee_region', 'employee_id', 'region_type', unique=True),
    )
    employee = relationship("Employee", back_populates="southern_seniority")

class Suspension(Base):
    __tablename__ = "suspensions"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    days = Column(Integer, nullable=False, CheckConstraint("days >= 0"))
    reason = Column(String(200))
    __table_args__ = (
        Index('idx_suspension_employee_period', 'employee_id', 'start_date', 'end_date', unique=True),
        CheckConstraint("end_date >= start_date"),
    )
    employee = relationship("Employee", back_populates="suspensions")

class EmployeeRankHistory(Base):
    __tablename__ = "employee_rank_history"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    rank_id = Column(Integer, ForeignKey("ranks.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False, index=True)
    assignment_date = Column(Date, nullable=False)
    end_date = Column(Date)
    __table_args__ = (
        Index('idx_rank_history_employee', 'employee_id', 'assignment_date', unique=True),
        CheckConstraint("end_date IS NULL OR end_date >= assignment_date"),
    )
    employee = relationship("Employee", back_populates="rank_history")
    rank = relationship("Rank")

class Aidictionary(Base):
    __tablename__ = "aidictionary"
    id = Column(Integer, primary_key=True)
    section = Column(String(50), nullable=False)
    key = Column(String(50), nullable=False)
    value = Column(Text, nullable=False)
    context = Column(String(50), default="general")
    __table_args__ = (
        Index('idx_section_key_context', 'section', 'key', 'context', unique=True),
    )

class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True)
    table_name = Column(String(50), nullable=False)
    column_name = Column(String(50), nullable=False)
    original_value = Column(String(100))
    corrected_value = Column(String(100))
    context = Column(String(50), default="general")
    recorded_at = Column(DateTime, default=datetime.utcnow)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    event_type = Column(String(50), nullable=False)
    event_data = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

class PatternRelations(Base):
    __tablename__ = "pattern_relations"
    id = Column(Integer, primary_key=True)
    pattern1_id = Column(Integer, ForeignKey("aidictionary.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    pattern2_id = Column(Integer, ForeignKey("aidictionary.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False, index=True)
    relation_strength = Column(Float, default=0.0, CheckConstraint("relation_strength >= -1 AND relation_strength <= 1"))
    __table_args__ = (
        Index('idx_pattern_relation', 'pattern1_id', 'pattern2_id', unique=True),
    )

class UserPreferences(Base):
    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), default="default_user", index=True)
    profile_name = Column(String(50), nullable=False)
    visible_columns = Column(Text, nullable=False)  # JSON string of selected columns
    sort_column = Column(String(50))
    sort_order = Column(String(10), default="ASC")
    context = Column(String(50), default="general")
    __table_args__ = (
        Index('idx_user_profile', 'user_id', 'profile_name', unique=True),
    )

def init_db():
    """تهيئة قاعدة البيانات مع إنشاء الجداول والفهارس."""
    Base.metadata.create_all(engine)
    with engine.connect() as conn:
        for table in Base.metadata.tables.values():
            for fk in table.foreign_keys:
                index_name = f"idx_{table.name}_{fk.column.name}"
                if index_name not in [idx.name for idx in table.indexes]:
                    conn.execute(text(f"CREATE INDEX {index_name} ON {table.name} ({fk.column.name})"))
        conn.commit()
    logger.info("Database initialized with dynamic schema and constraints.")

def get_sql_session():
    """إرجاع جلسة SQLAlchemy للتعامل مع قاعدة البيانات."""
    return SessionLocal()

if __name__ == "__main__":
    init_db()