"""Catalogue views: management."""

from ..common import *

@csrf_exempt
def product_list(request):
    if request.method == 'POST':
        # Retrieve form data
        code = request.POST.get('code')
        name = request.POST.get('name')
        size = request.POST.get('size')
        rate = float(request.POST.get('rate', 0) or 0)
        production_cost = float(request.POST.get('production_cost', 0) or 0)
        image_url = request.POST.get('image', '').strip()

        # Ensure all required fields are provided
        if code and name and size and rate is not None and production_cost is not None:
            product = Product.objects.create(
                code=code,
                name=name,
                size=size,
                rate=rate,
                add_stock=0,
                production_cost=production_cost,
                total_sales=0,
                total_stock=0,
                image=image_url if image_url else None
            )
            return redirect('product_list')
    
    # Fetch all products from the database
    products = Product.objects.all()
    return render(request, 'Product.html', {'products': products})

@csrf_exempt
def delete_product(request, product_id):
    if request.method == 'POST':
        try:
            product = Product.objects.get(id=product_id)
            product.delete()
        except Product.DoesNotExist:
            pass  # Optionally handle not found
    return redirect('product_list')

def upload_products(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        try:
            excel_file = request.FILES['excel_file']
            
            
            
            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # List of exact column names from the Excel file
            excel_column_names = ['Code', 'Name', 'Size', 'Rate', 'Add Stock', 'Production Cost', 'Total Sales', 'Total Stock']
            
            # Check for missing columns in the DataFrame
            missing_excel_columns = [col for col in excel_column_names if col not in df.columns]
            if missing_excel_columns:
                messages.error(request, f'Missing required columns in Excel file: {", ".join(missing_excel_columns)}. Please ensure your Excel has these exact column headers.')
                return redirect('upload_products')
            
            success_count = 0
            error_count = 0
            error_details = []
            
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
                    
                    success_count += 1
                    
                    
                except Exception as e:
                    error_count += 1
                    error_msg = f"Row {index + 2}: {str(e)}"
                    error_details.append(error_msg)
                    print(f"Error processing row {index + 2}: {str(e)}")
            
            if success_count > 0:
                messages.success(request, f'Successfully uploaded {success_count} products')
            if error_count > 0:
                messages.warning(request, f'Failed to upload {error_count} products')
                for error in error_details[:5]:  # Show first 5 errors
                    messages.error(request, error)
                if len(error_details) > 5:
                    messages.error(request, f"... and {len(error_details) - 5} more errors")
            
            return redirect('product_list')
            
        except Exception as e:
            error_msg = f'Error processing file: {str(e)}'
            print(error_msg)  # Print to console for debugging
            messages.error(request, error_msg)
            return redirect('upload_products')
            
    return render(request, 'upload_products.html')

@csrf_exempt
def update_product(request, product_id):
    if request.method == 'POST':
        try:
            product = Product.objects.get(id=product_id)
            for field in ['code', 'name', 'size', 'rate', 'production_cost', 'total_sales', 'total_stock']:
                value = request.POST.get(field)
                if value is not None:
                    if field in ['rate', 'production_cost', 'total_sales', 'total_stock']:
                        value = float(value or 0)
                    setattr(product, field, value)
            # Handle image URL
            image_url = request.POST.get('image', '').strip()
            if image_url:
                product.image = image_url
            elif 'image' in request.POST:
                # If image field is present but empty, clear it
                product.image = None
            product.save()
        except Product.DoesNotExist:
            pass
        return redirect('product_list')
    return redirect('product_list')
