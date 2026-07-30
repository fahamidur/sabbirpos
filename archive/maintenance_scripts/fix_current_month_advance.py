#!/usr/bin/env python3
# Script to fix current month advance calculation

# Read the file
with open('main/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change current month advance to use Customer.Advance (same as total)
content = content.replace(
    '            "current_month": current_month_advance_adai,',
    '            "current_month": total_advance,  # Use Customer.Advance for consistency'
)

# Change previous month advance to use Customer.Advance (same as total)
content = content.replace(
    '            "previous_month": previous_month_advance_adai,',
    '            "previous_month": total_advance,  # Use Customer.Advance for consistency'
)

# Also fix the mot_adai calculation for consistency
content = content.replace(
    '            "previous_month": previous_month_advance_adai+previous_month_due_adai+previous_month_payment_received,',
    '            "previous_month": total_advance+previous_month_due_adai+previous_month_payment_received,  # Use Customer.Advance for consistency'
)

content = content.replace(
    '            "current_month": current_month_advance_adai+current_month_due_adai+current_month_payment_received,',
    '            "current_month": total_advance+current_month_due_adai+current_month_payment_received,  # Use Customer.Advance for consistency'
)

# Write back
with open('main/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed current month advance to use Customer.Advance for consistency")
