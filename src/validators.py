"""
Validation utilities for LLM outputs
Ensures extracted data meets business rules and prevents hallucination
"""

import logging
from typing import Optional, List
from src.constants import (
    VALID_CATEGORIES, 
    VALID_PRIORITIES, 
    PRIORITY_ALIASES
)

logger = logging.getLogger(__name__)


class ExtractionValidator:
    """Validates LLM extraction outputs against allowed values"""
    
    @staticmethod
    def validate_category(category: str) -> Optional[str]:
        """
        Validate and normalize category value
        
        Args:
            category: LLM-extracted category
            
        Returns:
            Valid category or None if invalid
        """
        if not category:
            return None
        
        category_stripped = category.strip()
        
        # Exact match (case-sensitive)
        if category_stripped in VALID_CATEGORIES:
            return category_stripped
        
        # Case-insensitive match
        category_lower = category_stripped.lower()
        for valid in VALID_CATEGORIES:
            if valid.lower() == category_lower:
                logger.debug(f"Normalized category '{category}' to '{valid}'")
                return valid
        
        # Handle OUT_OF_SCOPE variations
        if "out" in category_lower and "scope" in category_lower:
            return "OUT_OF_SCOPE"
        
        logger.warning(f"Invalid category extracted: '{category}'. Returning None.")
        return None
    
    @staticmethod
    def validate_priority(priority: str) -> Optional[str]:
        """
        Validate and normalize priority value
        
        Args:
            priority: LLM-extracted priority
            
        Returns:
            Valid priority or None if invalid
        """
        if not priority:
            return None
        
        priority_stripped = priority.strip()
        
        # Exact match
        if priority_stripped in VALID_PRIORITIES:
            return priority_stripped
        
        # Case-insensitive match
        priority_lower = priority_stripped.lower()
        for valid in VALID_PRIORITIES:
            if valid.lower() == priority_lower:
                logger.debug(f"Normalized priority '{priority}' to '{valid}'")
                return valid
        
        # Try aliases
        if priority_lower in PRIORITY_ALIASES:
            normalized = PRIORITY_ALIASES[priority_lower]
            logger.debug(f"Mapped priority alias '{priority}' to '{normalized}'")
            return normalized
        
        logger.warning(f"Invalid priority extracted: '{priority}'. Returning None.")
        return None
    
    @staticmethod
    def validate_device(device: str, user_devices: List[str]) -> Optional[str]:
        """
        Validate device against user's registered devices
        
        Args:
            device: LLM-extracted device
            user_devices: List of valid user devices
            
        Returns:
            Valid device or None if not in list
        """
        if not device or not user_devices:
            return None
        
        device_stripped = device.strip()
        
        # Handle "None" string from LLM
        if device_stripped.lower() == "none":
            return None
        
        # Exact match (case-sensitive)
        if device_stripped in user_devices:
            return device_stripped
        
        # Case-insensitive match
        device_lower = device_stripped.lower()
        for valid_device in user_devices:
            if valid_device.lower() == device_lower:
                logger.debug(f"Case-normalized device '{device}' to '{valid_device}'")
                return valid_device
        
        logger.warning(f"Device '{device}' not in user's registered devices.")
        return None


def validate_extraction_result(
    extracted: dict, 
    user_devices: List[str] = None
) -> dict:
    """
    Validate all fields in an extraction result
    
    Args:
        extracted: Dict with extracted fields
        user_devices: List of valid user devices
        
    Returns:
        Dict with only valid fields
    """
    validated = {}
    
    if "category" in extracted:
        valid_cat = ExtractionValidator.validate_category(extracted["category"])
        if valid_cat:
            validated["category"] = valid_cat
    
    if "priority" in extracted:
        valid_priority = ExtractionValidator.validate_priority(extracted["priority"])
        if valid_priority:
            validated["priority"] = valid_priority
    
    if "device_id" in extracted and user_devices:
        valid_device = ExtractionValidator.validate_device(
            extracted["device_id"], 
            user_devices
        )
        if valid_device:
            validated["device_id"] = valid_device
    
    return validated
