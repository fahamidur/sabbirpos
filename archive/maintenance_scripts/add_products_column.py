#!/usr/bin/env python3
# Script to add formatted products column to filter_customer_sales

# Read the file
with open('main/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the filtered_sales section
old_section = '''        filtered_sales = [
            {
                'date': sale.date.strftime('%Y-%m-%d'),
                'salesman': sale.salesman.name if sale.salesman else '',
                'total_price': sale.total_price,
                'discount': sale.discount,
                'payment_received': sale.payment_received,
                'due': sale.due,
                'invoice_number': sale.invoice_number or 'N/A',
                'products': sale.products if sale.products else []
            }
            for sale in sales_records
        ]'''

new_section = '''        filtered_sales = []
        for sale in sales_records:
            # Format products into a readable string
            products_text = ""
            if sale.products:
                product_list = []
                for product in sale.products:
                    name = product.get('name', 'Unknown')
                    quantity = product.get('quantity', 0)
                    price = product.get('price', 0)
                    product_list.append(f"{name} (Qty: {quantity}, Price: {price})")
                products_text = " | ".join(product_list)
            else:
                products_text = "No products"
            
            filtered_sales.append({
                'date': sale.date.strftime('%Y-%m-%d'),
                'salesman': sale.salesman.name if sale.salesman else '',
                'total_price': sale.total_price,
                'discount': sale.discount,
                'payment_received': sale.payment_received,
                'due': sale.due,
                'invoice_number': sale.invoice_number or 'N/A',
                'products': sale.products if sale.products else [],
                'products_text': products_text  # New formatted column
            })'''

# Replace the section
content = content.replace(old_section, new_section)

# Write back
with open('main/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Added products_text column to filter_customer_sales function")
