#!/usr/bin/env python3
"""
system.py: يحتوي على المنطق التنفيذي ووظائف النظام لـ Reordering Sync Quantum Enhanced.
"""

import sys
import logging
import pandas as pd
import numpy as np
from rapidfuzz import fuzz
from dateutil import parser as date_parser
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtQml import QQmlApplicationEngine
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import text
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
from threading import Thread
import asyncio
import re
import numexpr
import json
from functools import lru_cache
from models import (init_db, get_sql_session, crud_operation, ReorderingTable, Employee, Rank, 
                   SectorialInstitutionGroup, Workplace, Promotion, Evaluation, ProfessionalExperience, 
                   SouthernSeniority, Suspension, EmployeeRankHistory, Aidictionary, Feedback, Event, 
                   PatternRelations, UserPreferences)

# إعداد السجلات
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ReorderingSyncQuantumEnhanced")

@lru_cache(maxsize=1000)
def calculate_total_seniority(employee_id: int, current_date: str = datetime.now().isoformat()) -> Dict:
    """حساب الأقدمية الكلية والمعتمدة لموظف مع التخزين المؤقت."""
    current_date = datetime.fromisoformat(current_date).date()
    with get_sql_session() as session:
        employee = session.query(Employee).options(
            joinedload(Employee.promotions),
            joinedload(Employee.professional_experience),
            joinedload(Employee.southern_seniority),
            joinedload(Employee.suspensions)
        ).filter(Employee.id == employee_id).first()
        if not employee:
            logger.warning(f"No employee found with ID {employee_id}")
            return {"total": 0, "approved": 0, "southern": 0, "southern_exhausted": False}
        last_date = max((p.effective_date for p in employee.promotions), default=employee.hire_date)
        if last_date > current_date:
            logger.warning(f"Last date {last_date} is in the future for employee {employee_id}")
            days = 0
        else:
            days = (current_date - last_date).days
        exp_days = sum(exp.months * 30 for exp in employee.professional_experience if not exp.applied)
        south_days = sum(s.additional_months * 30 for s in employee.southern_seniority if not s.exhausted and s.region_type in [3, 4])
        south_exhausted = all(s.exhausted for s in employee.southern_seniority if s.region_type in [3, 4])
        suspension_days = sum(s.days for s in employee.suspensions)
        total = max(0, days + exp_days + south_days)
        approved = max(0, total - suspension_days)
        if suspension_days > total:
            logger.warning(f"Suspensions ({suspension_days} days) exceed total seniority ({total} days) for employee {employee_id}")
            approved = 0
        logger.debug(f"Seniority calculation for employee {employee_id}: total={total}, approved={approved}, southern={south_days}")
        return {"total": total, "approved": approved, "southern": south_days, "southern_exhausted": south_exhausted}

@lru_cache(maxsize=1000)
def calculate_indice(category: int, grade: int, year: int) -> int:
    """حساب الرقم الاستدلالي مع التخزين المؤقت."""
    try:
        base = category * 100
        adjustments = {2021: 0, 2022: 50, 2023: 125, 2024: 200, 2025: 275}
        adjustment = adjustments.get(year, 0)
        raw_value = base + adjustment + (grade - 1) * (base + adjustment) * 0.05
        indice = int(round(raw_value))
        logger.debug(f"Indice calculation: category={category}, grade={grade}, year={year}, result={indice}")
        return indice
    except Exception as e:
        logger.error(f"Error calculating indice: {e}")
        return 0

def calculate_effective_date(employee_id: int, promotion_type: str, year: int) -> date:
    """حساب تاريخ السريان بناءً على نوع الترقية."""
    with get_sql_session() as session:
        employee = session.query(Employee).options(
            joinedload(Employee.promotions),
            joinedload(Employee.professional_experience),
            joinedload(Employee.southern_seniority)
        ).filter(Employee.id == employee_id).first()
        if not employee:
            logger.warning(f"No employee found with ID {employee_id} for effective date calculation")
            return datetime.strptime(f"{year}-01-01", "%Y-%m-%d").date()
        last_promotion = max((p.effective_date for p in employee.promotions), default=employee.hire_date)
        total_days = (datetime.strptime(f"{year - 1}-12-31", "%Y-%m-%d").date() - last_promotion).days
        exp_days = sum(exp.months * 30 for exp in employee.professional_experience if not exp.applied)
        south_days = sum(s.additional_months * 30 for s in employee.southern_seniority if not s.exhausted and s.region_type in [3, 4])
        all_periods = total_days + exp_days + south_days

        intervals = {"دنيا": 912, "متوسطة": 1095, "قصوى": 1278}
        pace_days = intervals.get(promotion_type, 912)
        remaining_days = all_periods - pace_days
        
        base_date = datetime.strptime(f"{year - 1}-12-31", "%Y-%m-%d").date()
        effective_date = base_date - timedelta(days=remaining_days)
        if effective_date < last_promotion:
            logger.warning(f"Effective date {effective_date} before last promotion {last_promotion}, adjusting")
            effective_date = last_promotion
        elif effective_date > base_date:
            logger.warning(f"Effective date {effective_date} exceeds reference date {base_date}, adjusting")
            effective_date = base_date
        logger.debug(f"Effective date for employee {employee_id}: {effective_date}")
        return effective_date

def calculate_financial_effect_date(effective_date: date) -> date:
    """حساب تاريخ الأثر المالي بناءً على تاريخ السريان."""
    try:
        if 1 <= effective_date.day <= 15:
            financial_date = effective_date.replace(day=1)
        else:
            new_month = effective_date.month + 1 if effective_date.month < 12 else 1
            new_year = effective_date.year + 1 if effective_date.month == 12 else effective_date.year
            financial_date = effective_date.replace(day=1, month=new_month, year=new_year)
        logger.debug(f"Financial effect date for {effective_date}: {financial_date}")
        return financial_date
    except Exception as e:
        logger.error(f"Error calculating financial effect date: {e}")
        return effective_date

def calculate_new_effective_date(effective_date: date, total_seniority: int, promotion_type: str) -> date:
    """حساب تاريخ السريان الجديد بناءً على الأقدمية."""
    try:
        intervals = {"دنيا": 912, "متوسطة": 1095, "قصوى": 1278}
        required = intervals.get(promotion_type, 912)
        if total_seniority < required:
            return effective_date
        remaining = max(total_seniority - required, 0)
        new_eff = effective_date + timedelta(days=total_seniority - remaining)
        if 1 <= new_eff.day <= 15:
            new_eff = new_eff.replace(day=1)
        else:
            new_month = new_eff.month + 1 if new_eff.month < 12 else 1
            new_year = new_eff.year + 1 if new_eff.month == 12 else new_eff.year
            new_eff = new_eff.replace(day=1, month=new_month, year=new_year)
        logger.debug(f"New effective date: {new_eff}")
        return new_eff
    except Exception as e:
        logger.error(f"Error calculating new effective date: {e}")
        return effective_date

def crud_operation(operation: str, table_name: str, data: Dict = None, filters: Dict = None) -> any:
    """تنفيذ عمليات CRUD على قاعدة البيانات مع معالجة التواريخ."""
    with get_sql_session() as session:
        try:
            tables = {
                "reordering_table": ReorderingTable, "employees": Employee, "ranks": Rank,
                "sectorial_institution_groups": SectorialInstitutionGroup, "workplaces": Workplace,
                "promotions": Promotion, "evaluations": Evaluation, "professional_experience": ProfessionalExperience,
                "southern_seniority": SouthernSeniority, "suspensions": Suspension, "employee_rank_history": EmployeeRankHistory,
                "aidictionary": Aidictionary, "feedback": Feedback, "events": Event, "pattern_relations": PatternRelations,
                "user_preferences": UserPreferences
            }
            model = tables.get(table_name)
            if not model:
                raise ValueError(f"Table {table_name} not supported")

            if operation == "create":
                processed_data = {}
                for k, v in data.items():
                    if k in ["birth_date", "hire_date", "effective_date", "start_date", "end_date", "promotion_date", "assignment_date", "new_effective_date", "financial_effect_date", "custom_date1", "custom_date2"] and v:
                        try:
                            processed_data[k] = date_parser.parse(str(v), dayfirst=True).date()
                        except ValueError:
                            logger.error(f"Invalid date format for {k}: {v}")
                            processed_data[k] = None
                    else:
                        processed_data[k] = v
                instance = model(**processed_data)
                session.add(instance)
                session.commit()
                return instance

            elif operation == "read":
                query = session.query(model)
                if filters:
                    for key, value in filters.items():
                        if key in ["birth_date", "hire_date", "effective_date", "start_date", "end_date", "promotion_date", "assignment_date", "new_effective_date", "financial_effect_date", "custom_date1", "custom_date2"] and value:
                            try:
                                query = query.filter(getattr(model, key) == date_parser.parse(str(value), dayfirst=True).date())
                            except ValueError:
                                logger.error(f"Invalid date filter for {key}: {value}")
                                continue
                        else:
                            query = query.filter(getattr(model, key) == value)
                return query.all()

            elif operation == "update":
                instance = session.query(model).filter_by(**filters).first()
                if not instance:
                    raise ValueError("Record not found")
                for key, value in data.items():
                    if key in ["birth_date", "hire_date", "effective_date", "start_date", "end_date", "promotion_date", "assignment_date", "new_effective_date", "financial_effect_date", "custom_date1", "custom_date2"] and value:
                        try:
                            setattr(instance, key, date_parser.parse(str(value), dayfirst=True).date())
                        except ValueError:
                            logger.error(f"Invalid date format for {key}: {value}")
                            setattr(instance, key, None)
                    else:
                        setattr(instance, key, value)
                session.commit()
                return instance

            elif operation == "delete":
                instance = session.query(model).filter_by(**filters).first()
                if not instance:
                    return False
                session.delete(instance)
                session.commit()
                return True

        except Exception as e:
            session.rollback()
            logger.error(f"CRUD operation error on table {table_name}: {e}")
            raise

class AidictionaryManager:
    def __init__(self):
        self.rules = {}

    def get_mapping(self, column: str, raw_value: str, context: str = "general") -> Optional[str]:
        """استرجاع قاعدة التصنيف من القاموس الذكي."""
        col = column.lower().strip()
        val = str(raw_value).strip().lower()
        with get_sql_session() as session:
            entry = session.query(Aidictionary).filter_by(section="col_mappings", key=f"{col}:{val}", context=context).first()
            return entry.value if entry else None

    def update_mapping(self, column: str, raw_value: str, standard_value: str, context: str = "general"):
        """تحديث قاعدة التصنيف في القاموس الذكي."""
        col = column.lower().strip()
        val = str(raw_value).strip().lower()
        std_val = str(standard_value).strip().lower()
        rule = f"{val} -> {std_val}"
        with get_sql_session() as session:
            entry = session.query(Aidictionary).filter_by(section="col_mappings", key=f"{col}:{val}", context=context).first()
            if not entry:
                crud_operation("create", "aidictionary", data={"section": "col_mappings", "key": f"{col}:{val}", "value": rule, "context": context})
            else:
                crud_operation("update", "aidictionary", data={"value": rule}, filters={"section": "col_mappings", "key": f"{col}:{val}", "context": context})
            logger.info(f"Updated Aidictionary: {col}:{val} -> {std_val} (context: {context})")

    def update_section(self, section: str, key: str, rule_text: str, context: str = "general"):
        """تحديث قسم معين في القاموس الذكي."""
        with get_sql_session() as session:
            entry = session.query(Aidictionary).filter_by(section=section, key=key, context=context).first()
            if not entry:
                crud_operation("create", "aidictionary", data={"section": section, "key": key, "value": rule_text, "context": context})
            else:
                crud_operation("update", "aidictionary", data={"value": rule_text}, filters={"section": section, "key": key, "context": context})
            logger.info(f"Updated section: {section}:{key} -> {rule_text} (context: {context})")

    def get_section(self, section: str, key: str, context: str = "general") -> str:
        """استرجاع قاعدة من قسم معين في القاموس الذكي."""
        with get_sql_session() as session:
            entry = session.query(Aidictionary).filter_by(section=section, key=key, context=context).first()
            return entry.value if entry else ""

    def parse_rule(self, rule_text: str, row: pd.Series, df: pd.DataFrame = None) -> Optional[Dict]:
        """تحليل قاعدة ذكية وتطبيقها على صف البيانات."""
        if not rule_text:
            return None
        match = re.match(r"(\w+(?:\s+\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?)?)\s+->\s+(.+)", rule_text)
        if not match:
            return None
        rule_type, targets = match.groups()
        target_cols = targets.split()

        if rule_type == "repeat_text":
            for col in row.index:
                if pd.notna(row[col]):
                    text = str(row[col]).lower()
                    if any(keyword in text for keyword in ["مؤسسة", "دار", "مركز", "بيت"]):
                        return {target_cols[0]: row[col]}
        elif rule_type == "match_rank":
            rank_names = [r.name.lower() for r in crud_operation("read", "ranks")]
            for col in row.index:
                if pd.notna(row[col]):
                    text = str(row[col]).lower()
                    if any(fuzz.partial_ratio(text, rank) >= 90 for rank in rank_names):
                        return {target_cols[0]: row[col]}
        elif rule_type == "other_text":
            excluded = ["institution_name", "rank_name", "current_grade", "new_grade", "effective_date", "new_effective_date", "points", "custom_text1", "custom_text2"]
            for col in row.index:
                if col not in excluded and pd.notna(row[col]):
                    text = str(row[col])
                    parts = text.split(maxsplit=1)
                    if len(parts) == 2 and len(target_cols) == 2:
                        return {target_cols[0]: parts[0], target_cols[1]: parts[1]}
                    elif len(target_cols) == 1:
                        return {target_cols[0]: text}
        elif rule_type.startswith("date_diff"):
            match_diff = re.match(r"date_diff\s+(\d+\.?\d*)-(\d+\.?\d*)", rule_type)
            if match_diff:
                min_years, max_years = map(float, match_diff.groups())
                min_days, max_days = min_years * 365, max_years * 365
                date_cols = [col for col, dtype in self._infer_column_types(df).items() if dtype == "date"]
                for i, col1 in enumerate(date_cols):
                    for col2 in date_cols[i+1:]:
                        if pd.notna(row[col1]) and pd.notna(row[col2]):
                            try:
                                d1 = pd.to_datetime(row[col1])
                                d2 = pd.to_datetime(row[col2])
                                diff_days = abs((d2 - d1).days)
                                if min_days <= diff_days <= max_days:
                                    older, newer = (col1, col2) if d1 < d2 else (col2, col1)
                                    return {target_cols[0]: row[older], target_cols[1]: row[newer]}
                            except Exception:
                                continue
        elif rule_type == "grade_relation":
            num_cols = [col for col in row.index if pd.to_numeric(row[col], errors='coerce').notna()]
            for i, col1 in enumerate(num_cols):
                for col2 in num_cols[i+1:]:
                    try:
                        val1 = float(row[col1])
                        val2 = float(row[col2])
                        if val1 <= 12 and val2 == val1 + 1:
                            return {target_cols[0]: val1, target_cols[1]: val2}
                    except Exception:
                        continue
        elif rule_type == "decimal_numbers":
            for col in row.index:
                if pd.notna(row[col]):
                    try:
                        val = float(row[col])
                        if val % 1 != 0:
                            return {target_cols[0]: val}
                    except Exception:
                        continue
        return None

    def _infer_column_types(self, df: pd.DataFrame) -> dict:
        """استنتاج أنواع الأعمدة في إطار البيانات."""
        types = {}
        for col in df.columns:
            series = df[col]
            if pd.api.types.is_numeric_dtype(series):
                types[col] = "number"
            else:
                try:
                    sample = series.dropna().astype(str).head(10).tolist()
                    date_count = sum(1 for s in sample if pd.to_datetime(s, errors='coerce') is not pd.NaT)
                    types[col] = "date" if sample and (date_count / len(sample)) >= 0.8 else "text"
                except Exception:
                    types[col] = "text"
        return types

class FeedbackManager:
    def record_feedback(self, table: str, column: str, original_value: str, corrected_value: str, context: str = "general"):
        """تسجيل التغذية الراجعة من المستخدم."""
        try:
            with get_sql_session() as session:
                crud_operation("create", "feedback", data={
                    "table_name": table, "column_name": column, 
                    "original_value": str(original_value), "corrected_value": str(corrected_value), 
                    "context": context
                })
                logger.info(f"Feedback recorded for '{column}' in table '{table}': '{original_value}' -> '{corrected_value}' (context: {context})")
        except Exception as e:
            logger.error(f"Error recording feedback: {e}")

    def get_feedback(self, context: str = "general") -> List[Dict]:
        """استرجاع التغذية الراجعة بناءً على السياق."""
        with get_sql_session() as session:
            return [{"table": f.table_name, "column": f.column_name, "original": f.original_value, "corrected": f.corrected_value, "context": f.context} 
                    for f in crud_operation("read", "feedback", filters={"context": context})]

class ContentBasedColumnClassifier:
    def __init__(self):
        self.vectorizer = TfidfVectorizer()
        self.classifier = RandomForestClassifier(n_estimators=100, random_state=42)
        self._train_model()

    def _train_model(self):
        """تدريب المصنف بناءً على التغذية الراجعة."""
        feedback = FeedbackManager().get_feedback()
        if feedback:
            texts = [" ".join([f["original"], f["corrected"]]) for f in feedback]
            labels = [f["column"] for f in feedback]
            if texts and labels:
                X = self.vectorizer.fit_transform(texts)
                self.classifier.fit(X, labels)
                logger.info("Column classifier trained successfully")
            else:
                logger.warning("No valid feedback data for training classifier")
        else:
            logger.warning("No feedback data for training classifier")

    def classify_column(self, series: pd.Series) -> str:
        """تصنيف عمود بناءً على محتواه."""
        samples = series.dropna().astype(str).head(10).tolist()
        if not samples:
            logger.warning("No sufficient data to classify column")
            return "unknown"
        text = " ".join(samples)
        X_test = self.vectorizer.transform([text])
        predicted = self.classifier.predict(X_test)[0]
        logger.debug(f"Column classified as: {predicted}")
        return predicted

    def active_fine_tune(self, feedback_data: List[Dict], epochs: int = 1):
        """إعادة تدريب المصنف بناءً على تغذية راجعة جديدة."""
        logger.info(f"Starting active fine-tuning with {len(feedback_data)} feedback entries...")
        texts = [" ".join([f["original"], f["corrected"]]) for f in feedback_data]
        labels = [f["column"] for f in feedback_data]
        if texts and labels:
            X = self.vectorizer.fit_transform(texts)
            for epoch in range(epochs):
                self.classifier.fit(X, labels)
                logger.info(f"Active fine-tuning - Epoch {epoch+1}/{epochs}...")
            logger.info("Active fine-tuning completed successfully")

class AdvancedSmartImporter:
    def __init__(self, table_name="reordering_table"):
        self.table_name = table_name
        self.column_classifier = ContentBasedColumnClassifier()
        self.aidict_manager = AidictionaryManager()
        self.feedback_manager = FeedbackManager()
        self.suggested_rules = []
        self.context = "general"
        self.recent_contexts = []  # ذاكرة سياقية قصيرة المدى
        self.learning_thread = Thread(target=self._continuous_learning, daemon=True)
        self.learning_thread.start()

    def _continuous_learning(self):
        """التعلم المستمر في خيط خلفي."""
        while True:
            try:
                asyncio.run(asyncio.sleep(300))  # 5 دقائق
                feedback = self.feedback_manager.get_feedback(self.context)
                if feedback:
                    self.update_dynamic_rules(feedback)
                    self.column_classifier.active_fine_tune(feedback)
            except Exception as e:
                logger.error(f"Continuous learning error: {e}")

    def update_dynamic_rules(self, feedback_data: List[Dict]):
        """تحديث القواعد الذكية بناءً على التغذية الراجعة."""
        with get_sql_session() as session:
            rule_counts = {}
            for entry in feedback_data:
                col = entry["column"]
                orig = entry["original"]
                corr = entry["corrected"]
                if col and orig and corr and orig != corr:
                    key = (col, orig, corr)
                    rule_counts[key] = rule_counts.get(key, 0) + 1
                    if rule_counts[key] >= 3:
                        self.aidict_manager.update_mapping(col, orig, corr, self.context)
                        pattern1 = session.query(Aidictionary).filter_by(section="col_mappings", key=f"{col}:{orig}", context=self.context).first()
                        if pattern1:
                            relation = session.query(PatternRelations).filter_by(pattern1_id=pattern1.id).first()
                            if relation:
                                crud_operation("update", "pattern_relations", data={"relation_strength": relation.relation_strength + 0.1}, filters={"id": relation.id})
                            else:
                                crud_operation("create", "pattern_relations", data={"pattern1_id": pattern1.id, "pattern2_id": pattern1.id, "relation_strength": 0.1})
                        logger.info(f"Dynamic rule updated from feedback: {col}:{orig} -> {corr} (repetitions: {rule_counts[key]})")
                        self.suggested_rules.append({"key": f"infer_{col}_{orig}", "rule": f"{orig} -> {corr}", "repetitions": rule_counts[key]})

    def standardize_value(self, column: str, value: str, data_type: str = "text") -> str:
        """توحيد قيمة عمود بناءً على نوع البيانات."""
        if pd.isna(value):
            logger.warning(f"Empty value in column {column}")
            return ""
        mapped = self.aidict_manager.get_mapping(column, value, self.context)
        if mapped:
            logger.info(f"[{column}] Retrieved from Aidictionary: '{value}' -> '{mapped}'")
            return mapped
        try:
            if data_type == "date":
                dt = date_parser.parse(str(value), dayfirst=True)
                standardized = dt.strftime("%Y-%m-%d")
            elif data_type == "number":
                standardized = str(float(value))
            else:
                standardized = str(value).strip()
            self.aidict_manager.update_mapping(column, value, standardized, self.context)
            logger.info(f"[{column}] Standardized '{value}' -> '{standardized}'")
            return standardized
        except Exception as e:
            logger.error(f"Error standardizing value '{value}' in column '{column}': {e}")
            return str(value)

    def analyze_table(self, df: pd.DataFrame, context: str = "general", initial_run: bool = True) -> dict:
        """تحليل إطار بيانات واستنتاج هيكله وقواعده."""
        self.context = context
        if context not in self.recent_contexts:
            self.recent_contexts.append(context)
            if len(self.recent_contexts) > 5:
                self.recent_contexts.pop(0)
        structure = {
            "num_rows": len(df),
            "num_columns": len(df.columns),
            "columns": list(df.columns),
            "dtypes": df.dtypes.apply(lambda x: x.name).to_dict(),
            "missing_values": df.isnull().sum().to_dict(),
            "unique_counts": df.nunique().to_dict(),
            "inferred_types": self._infer_column_types(df)
        }
        logger.debug(f"Table structure inferred: {structure}")
        content_types = self.classify_columns_by_content(df)
        structure["content_based_types"] = content_types
        sample = df.head(10)
        inferred_rules = {}
        self.suggested_rules = []

        if initial_run:
            num_cols = [col for col, dtype in structure["inferred_types"].items() if dtype == "number"]
            grade_pairs = []
            for i, col1 in enumerate(num_cols):
                for col2 in num_cols[i+1:]:
                    matches = 0
                    total = 0
                    for _, row in sample.iterrows():
                        try:
                            val1 = float(row[col1])
                            val2 = float(row[col2])
                            if val1 <= 12 and val2 == val1 + 1:
                                matches += 1
                            total += 1
                        except Exception:
                            continue
                    if total > 0 and matches / total >= 0.8:
                        grade_pairs.append((col1, col2))
                        inferred_rules["infer_grades"] = "grade_relation -> current_grade new_grade"
                        self.aidict_manager.update_section("row_rules", "infer_grades", inferred_rules["infer_grades"], context)
                        logger.info(f"Inferred grade relation rule: {inferred_rules['infer_grades']} (context: {context})")

            date_cols = [col for col, dtype in structure["inferred_types"].items() if dtype == "date"]
            date_pairs = []
            for i, col1 in enumerate(date_cols):
                for col2 in date_cols[i+1:]:
                    matches = 0
                    total = 0
                    for _, row in sample.iterrows():
                        try:
                            d1 = pd.to_datetime(row[col1])
                            d2 = pd.to_datetime(row[col2])
                            diff_days = abs((d2 - d1).days)
                            if 912 <= diff_days <= 1278:
                                matches += 1
                            total += 1
                        except Exception:
                            continue
                    if total > 0 and matches / total >= 0.8:
                        date_pairs.append((col1, col2))
                        inferred_rules["infer_effective_dates"] = "date_diff 2.5-3.5 -> effective_date new_effective_date"
                        self.aidict_manager.update_section("row_rules", "infer_effective_dates", inferred_rules["infer_effective_dates"], context)
                        logger.info(f"Inferred effective date rule: {inferred_rules['infer_effective_dates']} (context: {context})")

            text_cols = [col for col, dtype in structure["inferred_types"].items() if dtype == "text"]
            rank_names = [r.name.lower() for r in crud_operation("read", "ranks")]
            institution_keywords = ["مؤسسة", "دار", "مركز", "بيت"]
            for col in text_cols:
                sample_values = sample[col].dropna().astype(str).str.lower().tolist()
                if sample_values:
                    institution_count = sum(1 for val in sample_values for keyword in institution_keywords if keyword in val)
                    rank_count = sum(1 for val in sample_values for rank in rank_names if fuzz.partial_ratio(val, rank) >= 90)
                    total = len(sample_values)
                    if total > 0:
                        if institution_count / total >= 0.5:
                            inferred_rules["infer_institution"] = "repeat_text -> institution_name"
                            self.aidict_manager.update_section("row_rules", "infer_institution", inferred_rules["infer_institution"], context)
                            logger.info(f"Inferred institution rule: {inferred_rules['infer_institution']} (context: {context})")
                        elif rank_count / total >= 0.5:
                            inferred_rules["infer_rank"] = "match_rank -> rank_name"
                            self.aidict_manager.update_section("row_rules", "infer_rank", inferred_rules["infer_rank"], context)
                            logger.info(f"Inferred rank rule: {inferred_rules['infer_rank']} (context: {context})")
                        else:
                            inferred_rules["infer_name"] = "other_text -> first_name last_name"
                            self.aidict_manager.update_section("row_rules", "infer_name", inferred_rules["infer_name"], context)
                            logger.info(f"Inferred name rule: {inferred_rules['infer_name']} (context: {context})")

            for col in num_cols:
                sample_values = sample[col].dropna().astype(str).tolist()
                decimal_count = sum(1 for val in sample_values if '.' in val and val.replace('.', '').isdigit())
                if decimal_count >= 2:
                    suggestion = "decimal_numbers -> points"
                    self.suggested_rules.append({"key": "infer_points", "rule": suggestion, "repetitions": decimal_count})
                    logger.info(f"Suggested rule: {suggestion} (repetitions: {decimal_count}, context: {context})")

        self.aidict_manager.update_section("col_types", self.table_name, content_types, context)
        structure["inferred_rules"] = inferred_rules
        structure["suggested_rules"] = self.suggested_rules
        
        table_class = "Reordering" if "employee_id" in content_types.values() else "Unknown"
        structure["table_classification"] = table_class
        self.aidict_manager.update_section("table_class", self.table_name, {"table_class": table_class}, context)
        logger.info(f"Table classified as: {table_class} (context: {context})")
        
        if initial_run:
            structure["context_stats"] = self.compute_context_stats(df)
        return structure

    def compute_context_stats(self, df: pd.DataFrame) -> Dict:
        """حساب إحصائيات سياق إطار البيانات."""
        stats = {}
        for col in df.columns:
            stats[col] = {
                "mean": float(df[col].mean()) if pd.api.types.is_numeric_dtype(df[col]) else None,
                "std": float(df[col].std()) if pd.api.types.is_numeric_dtype(df[col]) else None,
                "missing": int(df[col].isnull().sum()),
                "unique": int(df[col].nunique())
            }
        logger.debug(f"Computed context stats: {stats}")
        return stats

    def standardize_table(self, df: pd.DataFrame) -> pd.DataFrame:
        """توحيد بيانات إطار البيانات بناءً على القواعد الذكية."""
        df_copy = df.copy()
        inferred_types = self._infer_column_types(df_copy)
        
        for col, dtype in inferred_types.items():
            if col in df_copy.columns:
                df_copy[col] = df_copy[col].apply(lambda x: self.standardize_value(col, x, dtype) if pd.notna(x) else "")
        
        rules = ["infer_institution", "infer_rank", "infer_name", "infer_grades", "infer_effective_dates"]
        for rule_key in rules:
            rule_text = self.aidict_manager.get_section("row_rules", rule_key, self.context)
            if rule_text:
                for index, row in df_copy.iterrows():
                    result = self.aidict_manager.parse_rule(rule_text, row, df_copy)
                    if result:
                        for target, value in result.items():
                            df_copy.at[index, target] = value
        
        custom_rules = crud_operation("read", "aidictionary", filters={"section": "custom_rules", "context": self.context})
        for rule in custom_rules:
            self.apply_custom_rule(df_copy, rule.key, rule.value)
        
        return df_copy

    def apply_custom_rule(self, df: pd.DataFrame, rule_name: str, rule_text: str) -> None:
        """تطبيق قاعدة مخصصة على إطار البيانات باستخدام vectorization."""
        try:
            match = re.match(r"(\w+)\s*=\s*(.+)", rule_text)
            if not match:
                logger.warning(f"Invalid custom rule syntax: {rule_text}")
                return
            target_col, expression = match.groups()
            if target_col not in df.columns:
                logger.warning(f"Target column {target_col} not in dataframe for rule {rule_name}")
                return

            local_vars = {col: df[col] for col in df.columns if col in expression}
            for col in local_vars:
                if "date" in col.lower() or col in ["custom_date1", "custom_date2", "effective_date", "new_effective_date", "financial_effect_date"]:
                    local_vars[col] = pd.to_datetime(local_vars[col], errors='coerce')
            df[target_col] = numexpr.evaluate(expression, local_dict=local_vars)
            logger.info(f"Applied custom rule {rule_name}: {rule_text}")
        except Exception as e:
            logger.error(f"Error applying custom rule {rule_name}: {e}")

    def analyze_rule(self, rule_text: str) -> str:
        """تحليل قاعدة مخصصة وإرجاع تقرير عن صلاحيتها."""
        try:
            match = re.match(r"(\w+)\s*=\s*(.+)", rule_text)
            if not match:
                return "خطأ: صيغة القاعدة غير صحيحة، استخدم 'الهدف = التعبير'"
            target_col, expression = match.groups()
            if target_col not in ["custom_text1", "custom_text2", "custom_date1", "custom_date2"]:
                return "خطأ: الهدف يجب أن يكون أحد الأعمدة المخصصة (custom_text1, custom_text2, custom_date1, custom_date2)"
            used_cols = re.findall(r"\b\w+\b", expression)
            valid_cols = ["first_name", "last_name", "effective_date", "new_effective_date", "custom_date1", "custom_date2"]
            for col in used_cols:
                if col not in valid_cols and not col.isdigit() and col not in ["+", "-", "*", "/"]:
                    return f"خطأ: العمود {col} غير مدعوم في التعبير"
            return f"تحليل: القاعدة صالحة، سيتم تطبيقها على {target_col}"
        except Exception as e:
            return f"خطأ: تحليل القاعدة فشل - {str(e)}"

    def get_suggested_rules(self) -> List[Dict]:
        """إرجاع القواعد المقترحة من التحليل الذكي."""
        return self.suggested_rules

    async def compute_computed_state(self, year: int = 2025, context: str = "general") -> Dict:
        """حساب الحالة المحسوبة للموظفين بناءً على القواعد."""
        self.context = context
        with get_sql_session() as session:
            employees = session.query(Employee).options(
                joinedload(Employee.promotions),
                joinedload(Employee.evaluations),
                joinedload(Employee.professional_experience),
                joinedload(Employee.southern_seniority),
                joinedload(Employee.suspensions),
                joinedload(Employee.rank_history)
            ).all()
            ranks = crud_operation("read", "ranks")
            if not employees or not ranks:
                logger.warning("No sufficient data for employees or ranks to compute state")
                return {"employees": {}, "reordering": {}}
            
            rank_indices = {r.id: calculate_indice(r.category, r.base_indice, year) for r in ranks}
            state = {"employees": {}, "reordering": {}}
            
            for emp in employees:
                seniority = calculate_total_seniority(emp.id)
                points = sum(e.annual_points for e in emp.evaluations if e.evaluation_year <= year) / len([e for e in emp.evaluations if e.evaluation_year <= year]) if emp.evaluations else 0
                current_indice = calculate_indice(emp.rank_id, emp.last_degree, year)
                exp_years = sum(exp.months / 12 for exp in emp.professional_experience if exp.applied)
                suspension_impact = sum(s.days for s in emp.suspensions) / 365.0
                state["employees"][emp.id] = {
                    "name": f"{emp.first_name} {emp.last_name}",
                    "seniority": seniority,
                    "points": points,
                    "current_grade": emp.last_degree,
                    "current_indice": current_indice,
                    "rank_id": emp.rank_id,
                    "rank_indice": rank_indices.get(emp.rank_id, 0),
                    "experience_years": exp_years,
                    "suspension_impact": suspension_impact
                }

            grouped_employees = {}
            for emp_id, data in state["employees"].items():
                key = (data["rank_id"], data["current_grade"])
                score = data["seniority"]["approved"] + data["points"] - data["suspension_impact"] + (data["experience_years"] * 10)
                grouped_employees.setdefault(key, []).append((emp_id, score, data))

            for key, group in grouped_employees.items():
                group.sort(key=lambda x: x[1], reverse=True)
                total = len(group)
                
                if total == 1:
                    minima_count, media_count, maxima_count = 1, 0, 0
                elif total == 2:
                    minima_count, media_count, maxima_count = 2, 0, 0
                elif total == 3:
                    minima_count, media_count, maxima_count = 2, 1, 0
                elif total == 4:
                    minima_count, media_count, maxima_count = 2, 2, 0
                else:
                    minima_count = max(1, int(total * 0.4))
                    media_count = max(1, int(total * 0.4))
                    maxima_count = max(1, total - minima_count - media_count)
                
                if total < 5:
                    logger.info(f"Small group distribution ({total} employees): minima={minima_count}, media={media_count}, maxima={maxima_count}")
                
                for i, (emp_id, score, data) in enumerate(group):
                    pace = ("دنيا" if i < minima_count else 
                            "متوسطة" if i < minima_count + media_count else 
                            "قصوى")
                    if data["seniority"]["approved"] < 912:
                        pace = "غير مؤهل"
                    new_grade = data["current_grade"] + 1 if pace != "غير مؤهل" else data["current_grade"]
                    new_indice = calculate_indice(data["rank_id"], new_grade, year)
                    effective_date = calculate_effective_date(emp_id, pace, year)
                    new_effective_date = calculate_new_effective_date(effective_date, data["seniority"]["approved"], pace)
                    financial_effect_date = calculate_financial_effect_date(new_effective_date)
                    state["reordering"][emp_id] = {
                        "year": year,
                        "name": data["name"],
                        "total_seniority_days": data["seniority"]["total"],
                        "approved_seniority_days": data["seniority"]["approved"],
                        "suspension_days": data["seniority"]["total"] - data["seniority"]["approved"],
                        "southern_seniority_days": data["seniority"]["southern"],
                        "southern_seniority_exhausted": data["seniority"]["southern_exhausted"],
                        "points": data["points"],
                        "current_grade": data["current_grade"],
                        "current_indice": data["current_indice"],
                        "new_grade": new_grade,
                        "new_indice": new_indice,
                        "rank_indice": data["rank_indice"],
                        "promotion_type": pace,
                        "effective_date": effective_date.isoformat(),
                        "new_effective_date": new_effective_date.isoformat(),
                        "financial_effect_date": financial_effect_date.isoformat(),
                        "remaining_seniority": max(0, data["seniority"]["approved"] - {"دنيا": 912, "متوسطة": 1095, "قصوى": 1278}.get(pace, 0)),
                        "experience_years": data["experience_years"],
                        "suspension_impact": data["suspension_impact"],
                        "custom_text1": "",
                        "custom_text2": "",
                        "custom_date1": None,
                        "custom_date2": None,
                        "notes": f"Rank {key[0]}, Grade {key[1]}, Exp {data['experience_years']:.1f} years"
                    }
            return state

    def update_database(self, analysis_report: Dict, standardized_df: pd.DataFrame, year: int = 2025):
        """تحديث قاعدة البيانات بناءً على البيانات الموحدة."""
        with get_sql_session() as session:
            for _, row in standardized_df.iterrows():
                try:
                    employee_data = {
                        "first_name": row.get("first_name", "غير محدد") if pd.notna(row.get("first_name")) else "غير محدد",
                        "last_name": row.get("last_name", "غير محدد") if pd.notna(row.get("last_name")) else "غير محدد",
                        "birth_date": row.get("birth_date", "1900-01-01") if pd.notna(row.get("birth_date")) else "1900-01-01",
                        "hire_date": row.get("hire_date", "1900-01-01") if pd.notna(row.get("hire_date")) else "1900-01-01",
                        "region_type": row.get("region_type", 0) if pd.notna(row.get("region_type")) else 0,
                        "gender": row.get("gender", "غير محدد") if pd.notna(row.get("gender")) else "غير محدد",
                        "marital_status": row.get("marital_status", "غير محدد") if pd.notna(row.get("marital_status")) else "غير محدد",
                        "rank_id": row.get("rank_id", 1) if pd.notna(row.get("rank_id")) else 1,
                        "sectorial_institution_group_id": row.get("sectorial_institution_group_id", 1) if pd.notna(row.get("sectorial_institution_group_id")) else 1,
                        "workplace_id": row.get("workplace_id", 1) if pd.notna(row.get("workplace_id")) else 1,
                        "last_degree": row.get("current_grade", 0) if pd.notna(row.get("current_grade")) else 0
                    }
                    if employee_data["first_name"] == "غير محدد" or employee_data["birth_date"] == "1900-01-01":
                        logger.warning(f"Incomplete employee data: {row}")
                        continue
                    
                    employee = crud_operation("read", "employees", filters={"first_name": employee_data["first_name"], "birth_date": employee_data["birth_date"]})
                    if not employee:
                        employee = crud_operation("create", "employees", data=employee_data)
                    else:
                        employee = employee[0]
                    emp_id = employee.id

                    if "points" in row and pd.notna(row["points"]):
                        crud_operation("create", "evaluations", data={"employee_id": emp_id, "evaluation_year": year, "annual_points": float(row["points"])})

                    if "southern_seniority_days" in row and pd.notna(row["southern_seniority_days"]):
                        crud_operation("create", "southern_seniority", data={
                            "employee_id": emp_id,
                            "region_type": row.get("region_type", 3) if pd.notna(row.get("region_type")) else 3,
                            "additional_months": int(row["southern_seniority_days"]) // 30,
                            "exhausted": False
                        })

                    crud_operation("create", "events", data={"event_type": "Import", "event_data": json.dumps({"employee_id": emp_id, "year": year})})
                except Exception as e:
                    logger.error(f"Error updating database for row {row}: {e}")

    async def process_import(self, file_path: str, year: int = 2025, context: str = "general"):
        """استيراد بيانات من ملف Excel وتحديث قاعدة البيانات."""
        try:
            self.context = context
            chunk_size = 1000  # يمكن تعديلها ديناميكيًا بناءً على حجم الملف
            for chunk in pd.read_excel(file_path, chunksize=chunk_size):
                if chunk.empty:
                    logger.warning("Empty Excel chunk")
                    continue
                df_std = self.standardize_table(chunk)
                analysis_report = self.analyze_table(df_std, context)
                self.update_database(analysis_report, df_std, year)
                self.column_classifier.active_fine_tune(self.feedback_manager.get_feedback(context))
            await self.reorder_employees(year, context)
            logger.info(f"Successfully imported file {file_path} (context: {context})")
            return self.get_suggested_rules()
        except Exception as e:
            logger.error(f"Error importing file {file_path}: {e}")
            return []

    async def reorder_employees(self, year: int = 2025, context: str = "general"):
        """إعادة ترتيب الموظفين بناءً على الحالة المحسوبة."""
        with get_sql_session() as session:
            current_reorderings = {r.employee_id: {
                "year": r.year, "name": r.name, "total_seniority_days": r.total_seniority_days,
                "approved_seniority_days": r.approved_seniority_days, "suspension_days": r.suspension_days,
                "southern_seniority_days": r.southern_seniority_days,
                "southern_seniority_exhausted": r.southern_seniority_exhausted,
                "points": r.points, "current_grade": r.current_grade, "current_indice": r.current_indice,
                "new_grade": r.new_grade, "new_indice": r.new_indice, "rank_indice": r.rank_indice,
                "promotion_type": r.promotion_type, "effective_date": r.effective_date.isoformat(),
                "new_effective_date": r.new_effective_date.isoformat(), "financial_effect_date": r.financial_effect_date.isoformat(),
                "remaining_seniority": r.remaining_seniority, "experience_years": r.experience_years,
                "suspension_impact": r.suspension_impact, "custom_text1": r.custom_text1,
                "custom_text2": r.custom_text2, "custom_date1": r.custom_date1.isoformat() if r.custom_date1 else None,
                "custom_date2": r.custom_date2.isoformat() if r.custom_date2 else None, "notes": r.notes
            } for r in crud_operation("read", "reordering_table", filters={"year": year})}
            
            new_state = await self.compute_computed_state(year, context)
            if self.compare_states(current_reorderings, new_state["reordering"]):
                for emp_id, data in new_state["reordering"].items():
                    try:
                        existing = crud_operation("read", "reordering_table", filters={"employee_id": emp_id, "year": year})
                        if existing:
                            crud_operation("update", "reordering_table", data=data, filters={"id": existing[0].id})
                        else:
                            crud_operation("create", "reordering_table", data=data)
                        crud_operation("create", "events", data={"event_type": "Reorder", "event_data": json.dumps({"employee_id": emp_id, "year": year})})
                    except Exception as e:
                        logger.error(f"Error updating reordering for employee {emp_id}: {e}")
                logger.info(f"Reordering table synchronized for year {year} (context: {context})")

    def compare_states(self, current_state: Dict, new_state: Dict) -> bool:
        """مقارنة حالتين لتحديد ما إذا كان هناك تغيير."""
        return current_state != new_state

    def record_feedback(self, column: str, original_value: str, corrected_value: str, context: str = "general"):
        """تسجيل تغذية راجعة من المستخدم."""
        self.feedback_manager.record_feedback(self.table_name, column, original_value, corrected_value, context)

class ReorderingSyncQuantumBackend(QObject):
    """فئة الخلفية لربط الواجهة مع النظام."""
    tableUpdated = pyqtSignal(list)
    employeeDialogRequested = pyqtSignal(int)
    promotionsDialogRequested = pyqtSignal(int)
    rankDialogRequested = pyqtSignal(int)
    rulesSuggested = pyqtSignal(list)
    alert = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.engine = AdvancedSmartImporter(table_name="reordering_table")
        self.loop = asyncio.get_event_loop()
        self.thread = Thread(target=self._run_event_loop, daemon=True)
        self.thread.start()

    def _run_event_loop(self):
        """تشغيل حلقة الحدث في خيط منفصل."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    @pyqtSlot(str, str)
    def importData(self, file_url: str, context: str):
        """استيراد بيانات من ملف Excel."""
        local_path = file_url if isinstance(file_url, str) else file_url.toLocalFile()
        future = asyncio.run_coroutine_threadsafe(self.engine.process_import(local_path, 2025, context), self.loop)
        suggested_rules = future.result()
        self.tableUpdated.emit(self.get_reordering("", "name"))
        if suggested_rules:
            self.rulesSuggested.emit(suggested_rules)

    @pyqtSlot(str)
    def exportData(self, file_url: str):
        """تصدير البيانات إلى ملف Excel."""
        local_path = file_url if isinstance(file_url, str) else file_url.toLocalFile()
        asyncio.run_coroutine_threadsafe(self.export_to_excel(local_path), self.loop).result()

    @pyqtSlot()
    def printData(self):
        """طباعة البيانات إلى ملف PDF."""
        asyncio.run_coroutine_threadsafe(self.print_table(), self.loop).result()

    @pyqtSlot()
    def syncReordering(self):
        """مزامنة إعادة الترتيب."""
        asyncio.run_coroutine_threadsafe(self.engine.reorder_employees(), self.loop).result()
        self.tableUpdated.emit(self.get_reordering("", "name"))

    @pyqtSlot(int)
    def openEmployeeDialog(self, employee_id: int):
        """طلب فتح حوار تعديل بيانات الموظف."""
        self.employeeDialogRequested.emit(employee_id)

    @pyqtSlot(int)
    def openPromotionsDialog(self, employee_id: int):
        """طلب فتح حوار إدارة الترقيات."""
        self.promotionsDialogRequested.emit(employee_id)

    @pyqtSlot(int)
    def openRankDialog(self, employee_id: int):
        """طلب فتح حوار إدارة الرتب."""
        self.rankDialogRequested.emit(employee_id)

    @pyqtSlot(str, str, str, str)
    def saveRule(self, section: str, key: str, rule_text: str, context: str):
        """حفظ قاعدة أو دالة مخصصة."""
        self.engine.aidict_manager.update_section(section, key, rule_text, context)

    @pyqtSlot(str, result=str)
    def analyzeRule(self, rule_text: str):
        """تحليل قاعدة مخصصة قبل الحفظ."""
        return self.engine.analyze_rule(rule_text)

    @pyqtSlot(str, str)
    def acceptSuggestion(self, key: str, rule: str):
        """قبول اقتراح قاعدة ذكية."""
        self.engine.aidict_manager.update_section("row_rules", key, rule, self.engine.context)

    @pyqtSlot(str, str)
    def rejectSuggestion(self, key: str, rule: str):
        """رفض اقتراح قاعدة ذكية مع تقليل وزنها."""
        with get_sql_session() as session:
            entry = session.query(Aidictionary).filter_by(section="row_rules", key=key, context=self.engine.context).first()
            if entry:
                relation = session.query(PatternRelations).filter_by(pattern1_id=entry.id).first()
                if relation:
                    crud_operation("update", "pattern_relations", data={"relation_strength": relation.relation_strength - 0.1}, filters={"id": relation.id})

    @pyqtSlot(str, str, str, str, result=bool)
    def saveDisplaySettings(self, profile_name: str, visible_columns: list, sort_column: str, sort_order: str, context: str):
        """حفظ إعدادات العرض."""
        data = {
            "user_id": "default_user",
            "profile_name": profile_name,
            "visible_columns": json.dumps(visible_columns),
            "sort_column": sort_column,
            "sort_order": sort_order,
            "context": context
        }
        try:
            existing = crud_operation("read", "user_preferences", filters={"user_id": "default_user", "profile_name": profile_name})
            if existing:
                crud_operation("update", "user_preferences", data=data, filters={"id": existing[0].id})
            else:
                crud_operation("create", "user_preferences", data=data)
            return True
        except Exception as e:
            logger.error(f"Error saving display settings: {e}")
            return False

    @pyqtSlot(result=list)
    def getSavedProfiles(self):
        """استرجاع قائمة إعدادات العرض المحفوظة."""
        with get_sql_session() as session:
            profiles = crud_operation("read", "user_preferences", filters={"user_id": "default_user"})
            return [p.profile_name for p in profiles]

    @pyqtSlot(str, result=dict)
    def loadDisplaySettings(self, profile_name: str):
        """تحميل إعدادات العرض بناءً على الاسم."""
        with get_sql_session() as session:
            profile = crud_operation("read", "user_preferences", filters={"user_id": "default_user", "profile_name": profile_name})
            if profile:
                p = profile[0]
                return {
                    "visibleColumns": json.loads(p.visible_columns),
                    "sortColumn": p.sort_column,
                    "sortOrder": p.sort_order,
                    "context": p.context
                }
            return {"visibleColumns": [], "sortColumn": "", "sortOrder": "ASC", "context": "general"}

    @pyqtSlot(str)
    def deleteDisplaySettings(self, profile_name: str):
        """حذف إعدادات العرض بناءً على الاسم."""
        crud_operation("delete", "user_preferences", filters={"user_id": "default_user", "profile_name": profile_name})

    @pyqtSlot(int, result=bool)
    def isColumnVisible(self, column_index: int):
        """التحقق مما إذا كان العمود مرئيًا بناءً على الإعدادات."""
        with get_sql_session() as session:
            profile = crud_operation("read", "user_preferences", filters={"user_id": "default_user", "context": self.engine.context})
            if profile and profile[0].visible_columns:
                visible_columns = json.loads(profile[0].visible_columns)
                return self.all_columns()[column_index] in visible_columns
            return True

    @pyqtSlot(str, str, str, str, result=list)
    def getReordering(self, search_text: str, search_field: str, sort_column: str, sort_order: str) -> List:
        """استرجاع بيانات إعادة الترتيب مع دعم البحث والفرز."""
        try:
            with get_sql_session() as session:
                query = session.query(ReorderingTable).join(Employee).join(Rank).join(SectorialInstitutionGroup)
                if search_text:
                    if search_field == "name":
                        query = query.filter(or_(
                            Employee.first_name.ilike(f"%{search_text}%"),
                            Employee.last_name.ilike(f"%{search_text}%")
                        ))
                        reorderings = query.all()
                        filtered = [r for r in reorderings if fuzz.partial_ratio(f"{r.employee.first_name} {r.employee.last_name}".lower(), search_text.lower()) >= 90]
                    elif search_field == "rank_indice":
                        query = query.filter(Rank.name.ilike(f"%{search_text}%"))
                        reorderings = query.all()
                        filtered = [r for r in reorderings if fuzz.partial_ratio(r.employee.rank.name.lower(), search_text.lower()) >= 90]
                    elif search_field == "institution_name":
                        query = query.filter(SectorialInstitutionGroup.name.ilike(f"%{search_text}%"))
                        reorderings = query.all()
                        filtered = [r for r in reorderings if fuzz.partial_ratio(r.employee.sectorial_institution_group.name.lower(), search_text.lower()) >= 90]
                    else:
                        filtered = query.all()
                else:
                    filtered = query.all()

                if sort_column:
                    sort_attr = getattr(ReorderingTable, sort_column, None)
                    if sort_attr:
                        query = query.order_by(sort_attr.asc() if sort_order == "ASC" else sort_attr.desc())
                        filtered = query.all()

                return [{
                    "id": r.id, "year": r.year, "employee_id": r.employee_id, "name": f"{r.employee.first_name} {r.employee.last_name}",
                    "total_seniority_days": r.total_seniority_days, "approved_seniority_days": r.approved_seniority_days,
                    "suspension_days": r.suspension_days, "southern_seniority_days": r.southern_seniority_days,
                    "southern_seniority_exhausted": r.southern_seniority_exhausted, "points": r.points,
                    "current_grade": r.current_grade, "current_indice": r.current_indice, "new_grade": r.new_grade,
                    "new_indice": r.new_indice, "rank_indice": r.rank_indice, "promotion_type": r.promotion_type,
                    "effective_date": r.effective_date.isoformat(), "new_effective_date": r.new_effective_date.isoformat(),
                    "financial_effect_date": r.financial_effect_date.isoformat(),
                    "experience_years": r.experience_years, "suspension_impact": r.suspension_impact,
                    "custom_text1": r.custom_text1, "custom_text2": r.custom_text2,
                    "custom_date1": r.custom_date1.isoformat() if r.custom_date1 else "",
                    "custom_date2": r.custom_date2.isoformat() if r.custom_date2 else "", "notes": r.notes
                } for r in filtered]
        except Exception as e:
            logger.error(f"Error retrieving reordering table: {e}")
            self.alert.emit(f"خطأ في استرجاع البيانات: {str(e)}")
            return []

    @pyqtSlot(int, str, str, str)
    def updateEmployee(self, employee_id: int, first_name: str, last_name: str, birth_date: str):
        """تحديث بيانات موظف."""
        try:
            data = {"first_name": first_name, "last_name": last_name, "birth_date": birth_date}
            crud_operation("update", "employees", data=data, filters={"id": employee_id})
            self.tableUpdated.emit(self.get_reordering("", "name"))
        except Exception as e:
            logger.error(f"Error updating employee {employee_id}: {e}")
            self.alert.emit(f"خطأ في تحديث بيانات الموظف: {str(e)}")

    async def export_to_excel(self, file_path: str):
        """تصدير البيانات إلى ملف Excel."""
        try:
            with get_sql_session() as session:
                reorderings = crud_operation("read", "reordering_table")
                df = pd.DataFrame([{
                    "معرف": r.id, "السنة": r.year, "اسم الموظف": r.name, "الأقدمية الكلية": r.total_seniority_days,
                    "الأقدمية المعتمدة": r.approved_seniority_days, "أيام الإيقاف": r.suspension_days,
                    "خبرة الجنوب": r.southern_seniority_days, "خبرة الجنوب مستنفذة": "نعم" if r.southern_seniority_exhausted else "لا",
                    "النقاط": r.points, "الدرجة الحالية": r.current_grade, "الرقم الاستدلالي للدرجة الحالية": r.current_indice,
                    "الدرجة الجديدة": r.new_grade, "الرقم الاستدلالي للدرجة الجديدة": r.new_indice,
                    "الرقم الاستدلالي للرتبة": r.rank_indice, "نوع الترقية": r.promotion_type,
                    "تاريخ السريان": r.effective_date.isoformat(), "تاريخ السريان الجديد": r.new_effective_date.isoformat(),
                    "تاريخ الأثر المالي": r.financial_effect_date.isoformat(), "سنوات الخبرة": r.experience_years,
                    "تأثير الإيقاف": r.suspension_impact, "نص مخصص 1": r.custom_text1, "نص مخصص 2": r.custom_text2,
                    "تاريخ مخصص 1": r.custom_date1.isoformat() if r.custom_date1 else "", 
                    "تاريخ مخصص 2": r.custom_date2.isoformat() if r.custom_date2 else "", "ملاحظات": r.notes
                } for r in reorderings])
                df.to_excel(file_path, index=False)
                logger.info(f"Table exported to {file_path}")
        except Exception as e:
            logger.error(f"Error exporting table to Excel: {e}")
            self.alert.emit(f"خطأ في التصدير إلى Excel: {str(e)}")

    async def print_table(self, file_path: str = "reordering_report.pdf"):
        """طباعة البيانات إلى ملف PDF."""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table
            with get_sql_session() as session:
                reorderings = crud_operation("read", "reordering_table")
                doc = SimpleDocTemplate(file_path, pagesize=A4)
                data = [["معرف", "السنة", "الاسم", "الأقدمية الكلية", "خبرة الجنوب", "النقاط", "الدرجة الحالية", 
                         "الرقم الاستدلالي للدرجة الحالية", "الدرجة الجديدة", "الرقم الاستدلالي للدرجة الجديدة", 
                         "الرقم الاستدلالي للرتبة", "نوع الترقية", "تاريخ الأثر المالي", "سنوات الخبرة", "تأثير الإيقاف",
                         "نص مخصص 1", "نص مخصص 2", "تاريخ مخصص 1", "تاريخ مخصص 2"]]
                data.extend([[r.id, r.year, r.name, r.total_seniority_days, r.southern_seniority_days, r.points, r.current_grade, 
                              r.current_indice, r.new_grade, r.new_indice, r.rank_indice, r.promotion_type, 
                              r.financial_effect_date.isoformat(), r.experience_years, r.suspension_impact,
                              r.custom_text1, r.custom_text2, 
                              r.custom_date1.isoformat() if r.custom_date1 else "", 
                              r.custom_date2.isoformat() if r.custom_date2 else ""] 
                             for r in reorderings])
                table = Table(data)
                doc.build([table])
                logger.info(f"PDF report created at {file_path}")
        except Exception as e:
            logger.error(f"Error printing table to PDF: {e}")
            self.alert.emit(f"خطأ في طباعة الجدول: {str(e)}")

    @staticmethod
    def all_columns() -> list:
        """إرجاع قائمة بجميع الأعمدة الممكنة في جدول إعادة الترتيب."""
        return [
            "id", "year", "name", "total_seniority_days", "approved_seniority_days", "suspension_days",
            "southern_seniority_days", "southern_seniority_exhausted", "points", "current_grade",
            "current_indice", "new_grade", "new_indice", "rank_indice", "promotion_type",
            "effective_date", "new_effective_date", "financial_effect_date", "experience_years",
            "suspension_impact", "custom_text1", "custom_text2", "custom_date1", "custom_date2", "notes"
        ]

def launch_reordering_sync_quantum():
    """تشغيل النظام مع تحميل واجهة QML."""
    init_db()
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    backend = ReorderingSyncQuantumBackend()
    engine.rootContext().setContextProperty("backend", backend)
    with open("interface.qml", "r", encoding="utf-8") as f:
        engine.loadData(f.read().encode('utf-8'))
    if not engine.rootObjects():
        logger.error("Failed to load QML")
        sys.exit(-1)
    logger.info("Reordering Sync Quantum Enhanced launched successfully")
    sys.exit(app.exec())

if __name__ == "__main__":
    launch_reordering_sync_quantum()