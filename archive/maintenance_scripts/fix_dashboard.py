#!/usr/bin/env python3
# Script to fix dashboard advance calculation

# Read the file
with open('main/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Make the changes
# Change line 194: total_advance_adai to total_advance
content = content.replace(
    '            "all_time": total_advance_adai,',
    '            "all_time": total_advance,  # Use Customer.Advance instead of Adai advance'
)

# Change line 199: total_advance_adai to total_advance
content = content.replace(
    '            "all_time": total_advance_adai+total_due_adai+total_payment_received,',
    '            "all_time": total_advance+total_due_adai+total_payment_received,  # Use Customer.Advance instead of Adai advance'
)

# Write back
with open('main/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Dashboard fixed to use Customer.Advance instead of Adai advance")
