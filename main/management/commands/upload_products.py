from django.core.management.base import BaseCommand
from main.models import Product
import pandas as pd
import os

class Command(BaseCommand):
    help = 'Upload products from Excel file to database'

    def handle(self, *args, **options):
        try:
            # Path to the Excel file
            excel_file = 'main/produts_list.xlsx'
            
            # Check if file exists
            if not os.path.exists(excel_file):
                self.stdout.write(self.style.ERROR(f'Excel file not found at {excel_file}'))
                return

            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # List of exact column names from the Excel file
            excel_column_names = ['Code', 'Name', 'Size', 'Rate', 'Add Stock', 'Production Cost', 'Total Sales', 'Total Stock']
            
            # Check for missing columns in the DataFrame
            missing_excel_columns = [col for col in excel_column_names if col not in df.columns]
            if missing_excel_columns:
                self.stdout.write(self.style.ERROR(f'Missing required columns in Excel file: {", ".join(missing_excel_columns)}. Please ensure your Excel has these exact column headers.'))
                return

            # Counter for successful uploads
            success_count = 0
            error_count = 0
            error_details = []

            # Process each row
            for index, row in df.iterrows():
                try:
                    # Convert values to appropriate types and handle NaN using Excel column names
                    code = str(row['Code']) if pd.notna(row['Code']) else ''
                    name = str(row['Name']) if pd.notna(row['Name']) else ''
                    size = str(row['Size']) if pd.notna(row['Size']) else ''
                    rate = float(row['Rate']) if pd.notna(row['Rate']) else 0.0
                    add_stock = float(row['Add Stock']) if pd.notna(row['Add Stock']) else 0.0
                    production_cost = float(row['Production Cost']) if pd.notna(row['Production Cost']) else 0.0
                    total_sales = float(row['Total Sales']) if pd.notna(row['Total Sales']) else 0.0
                    total_stock = float(row['Total Stock']) if pd.notna(row['Total Stock']) else 0.0
                    
                    # Validate required fields
                    if not code or not name:
                        raise ValueError("Code and Name are required fields for each product.")

                    product, created = Product.objects.update_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'size': size,
                            'rate': rate,
                            'add_stock': add_stock,
                            'production_cost': production_cost,
                            'total_sales': total_sales,
                            'total_stock': total_stock
                        }
                    )
                    
                    if created:
                        self.stdout.write(self.style.SUCCESS(f'Created product: {product.name}'))
                    else:
                        self.stdout.write(self.style.SUCCESS(f'Updated product: {product.name}'))
                    
                    success_count += 1

                except Exception as e:
                    error_count += 1
                    error_msg = f"Row {index + 2}: {str(e)}"
                    error_details.append(error_msg)
                    self.stdout.write(self.style.ERROR(f'Error processing row {index + 2}: {str(e)}'))

            # Print summary
            self.stdout.write(self.style.SUCCESS(f'\nUpload completed:'))
            self.stdout.write(self.style.SUCCESS(f'Successfully processed: {success_count} products'))
            if error_count > 0:
                self.stdout.write(self.style.WARNING(f'Failed to process: {error_count} products'))
                for error in error_details:
                    self.stdout.write(self.style.ERROR(f"  - {error}"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error reading Excel file: {str(e)}')) 