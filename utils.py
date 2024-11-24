"""Utility functions for tax calculation and report generation."""
from models import TaxRule
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def calculate_tax(annual_income, deductions=None):
    """Calculate tax based on income and deductions."""
    try:
        if not isinstance(annual_income, (int, float)) or annual_income < 0:
            raise ValueError("Annual income must be a positive number")
            
        if deductions is None:
            deductions = {}
            
        # Validate deductions
        if not isinstance(deductions, dict):
            raise ValueError("Deductions must be a dictionary")
            
        for key, value in deductions.items():
            if not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"Invalid deduction value for {key}")
            
        # Get active tax rules ordered by min_income
        tax_rules = TaxRule.query.filter_by(is_active=True).order_by(TaxRule.min_income).all()
        if not tax_rules:
            raise ValueError("No active tax rules found")

        # Calculate total deductions
        total_deductions = sum(deductions.values())
        if total_deductions > annual_income:
            logger.warning(f"Total deductions ({total_deductions}) exceed annual income ({annual_income})")
        
        # Calculate taxable income
        taxable_income = max(0, annual_income - total_deductions)
        
        # Calculate tax
        total_tax = 0
        remaining_income = taxable_income
        tax_breakdown = []
        
        for rule in tax_rules:
            if remaining_income <= 0:
                break
                
            # Calculate income in this bracket
            if rule.max_income:
                income_in_bracket = min(remaining_income, rule.max_income - rule.min_income)
            else:
                income_in_bracket = remaining_income
            
            # Calculate tax for this bracket
            tax_in_bracket = income_in_bracket * (rule.tax_rate / 100)
            
            tax_breakdown.append({
                'min_income': rule.min_income,
                'max_income': rule.max_income,
                'tax_rate': rule.tax_rate,
                'income_in_bracket': income_in_bracket,
                'tax_amount': tax_in_bracket
            })
            
            total_tax += tax_in_bracket
            remaining_income -= income_in_bracket
            
        # Round tax amounts to 2 decimal places
        total_tax = round(total_tax, 2)
        for bracket in tax_breakdown:
            bracket['tax_amount'] = round(bracket['tax_amount'], 2)
            
        return {
            'annual_income': annual_income,
            'total_deductions': total_deductions,
            'taxable_income': taxable_income,
            'total_tax': total_tax,
            'effective_tax_rate': round((total_tax / annual_income * 100), 2) if annual_income > 0 else 0,
            'tax_breakdown': tax_breakdown,
            'calculation_date': datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Error in tax calculation: {str(e)}")
        raise

def generate_tax_report(calculation):
    """Generate a tax report from a calculation."""
    try:
        if not calculation or not isinstance(calculation.tax_result, dict):
            raise ValueError("Invalid calculation data")
            
        result = calculation.tax_result
        
        report = {
            'summary': {
                'annual_income': result.get('annual_income', 0),
                'total_deductions': result.get('total_deductions', 0),
                'taxable_income': result.get('taxable_income', 0),
                'total_tax': result.get('total_tax', 0),
                'effective_tax_rate': result.get('effective_tax_rate', 0)
            },
            'breakdown': result.get('tax_breakdown', []),
            'calculation_date': result.get('calculation_date', datetime.utcnow()),
            'tax_saving_tips': get_tax_saving_tips(result)
        }
        
        return report
        
    except Exception as e:
        logger.error(f"Error generating tax report: {str(e)}")
        raise

def get_tax_saving_tips(income_data):
    """Generate personalized tax saving tips based on income data."""
    try:
        tips = []
        annual_income = income_data.get('annual_income', 0)
        total_deductions = income_data.get('total_deductions', 0)
        
        # Basic deduction tip
        if total_deductions < 50000:  # Assuming 50000 is a reasonable deduction target
            tips.append({
                'category': 'Deductions',
                'tip': 'Consider maximizing your deductions through investments in tax-saving instruments.',
                'potential_savings': 'Up to ₹15,000 annually'
            })
            
        # High income tips
        if annual_income > 1000000:  # High income bracket
            tips.extend([
                {
                    'category': 'Investments',
                    'tip': 'Consider long-term investments in ELSS funds for tax benefits under Section 80C.',
                    'potential_savings': 'Up to ₹46,800 annually'
                },
                {
                    'category': 'Insurance',
                    'tip': 'Maximize tax benefits by investing in health insurance for yourself and dependents.',
                    'potential_savings': 'Up to ₹25,000 annually'
                }
            ])
            
        # Medium income tips
        elif annual_income > 500000:  # Medium income bracket
            tips.extend([
                {
                    'category': 'Savings',
                    'tip': 'Consider investing in PPF or NSC for long-term tax benefits.',
                    'potential_savings': 'Up to ₹31,200 annually'
                },
                {
                    'category': 'Home Loan',
                    'tip': 'If you have a home loan, ensure you are claiming both principal and interest deductions.',
                    'potential_savings': 'Varies based on loan amount'
                }
            ])
            
        # Low income tips
        else:
            tips.extend([
                {
                    'category': 'Basic Deductions',
                    'tip': 'Ensure you are claiming all eligible deductions under Section 80C.',
                    'potential_savings': 'Up to ₹15,600 annually'
                },
                {
                    'category': 'Retirement',
                    'tip': 'Consider contributing to NPS for additional tax benefits.',
                    'potential_savings': 'Up to ₹15,600 annually'
                }
            ])
            
        return tips
        
    except Exception as e:
        logger.error(f"Error generating tax saving tips: {str(e)}")
        return []
