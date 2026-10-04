from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class SchemeCleanedModel(BaseModel):
    """
    Pydantic validation model enforcing data integrity rules for cleaned schemes.
    """
    scheme_name: str = Field(..., description="Name of the government scheme")
    state: str = Field(default="Karnataka", description="State governing the scheme")
    department: Optional[str] = Field(default=None, description="Department administering the scheme")
    description: Optional[str] = Field(default=None, description="Full description of the scheme")
    benefits: List[str] = Field(default_factory=list, description="List of benefits provided")
    eligibility: List[str] = Field(default_factory=list, description="List of eligibility conditions")
    age_min: Optional[int] = Field(default=None, description="Minimum age requirement")
    age_max: Optional[int] = Field(default=None, description="Maximum age limit")
    income_min: Optional[float] = Field(default=None, description="Minimum family income limit")
    income_max: Optional[float] = Field(default=None, description="Maximum family income limit")
    occupation: List[str] = Field(default_factory=list, description="Eligible occupations")
    category: List[str] = Field(default_factory=list, description="Eligible social/economic categories")
    documents_required: List[str] = Field(default_factory=list, description="List of required documents")
    application_process: Optional[str] = Field(default=None, description="Step-by-step application instructions")
    official_url: Optional[str] = Field(default=None, description="Official portal URL")
    source_date: Optional[str] = Field(default=None, description="Date source data was scraped")
    last_updated: Optional[str] = Field(default=None, description="Last updated timestamp")

    @field_validator("scheme_name")
    @classmethod
    def check_scheme_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("scheme_name must not be empty")
        return v.strip()

    @field_validator("benefits", "eligibility", "occupation", "category", "documents_required", mode="before")
    @classmethod
    def clean_and_deduplicate_list(cls, v) -> List[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        seen = set()
        cleaned_list = []
        for item in v:
            if item and isinstance(item, str) and item.strip():
                clean_item = item.strip()
                norm_item = clean_item.lower()
                if norm_item not in seen:
                    seen.add(norm_item)
                    cleaned_list.append(clean_item)
        return cleaned_list

    @model_validator(mode="after")
    def validate_ranges(self):
        # Validate age bounds
        if self.age_min is not None and self.age_max is not None:
            if self.age_min > self.age_max:
                raise ValueError(f"age_min ({self.age_min}) cannot be greater than age_max ({self.age_max})")

        # Validate income bounds
        if self.income_min is not None and self.income_max is not None:
            if self.income_min > self.income_max:
                raise ValueError(f"income_min ({self.income_min}) cannot be greater than income_max ({self.income_max})")

        return self


def validate_scheme_dict(data: dict) -> SchemeCleanedModel:
    """Validates raw extracted dict against Pydantic schema."""
    return SchemeCleanedModel(**data)
