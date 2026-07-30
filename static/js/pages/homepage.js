document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
        
        // Cart Management System
        function getCart() {
            const cart = localStorage.getItem('ecommerce_cart');
            return cart ? JSON.parse(cart) : [];
        }
        
        function saveCart(cart) {
            localStorage.setItem('ecommerce_cart', JSON.stringify(cart));
            updateCartBadge();
        }
        
        function updateCartBadge() {
            const cart = getCart();
            const badge = document.getElementById('cartBadge');
            const floatingBadge = document.getElementById('floatingCartBadge');
            const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
            if (totalItems > 0) {
                if (badge) {
                    badge.textContent = totalItems;
                    badge.style.display = 'inline-block';
                }
                if (floatingBadge) {
                    floatingBadge.textContent = totalItems;
                    floatingBadge.style.display = 'flex';
                }
            } else {
                if (badge) {
                    badge.style.display = 'none';
                }
                if (floatingBadge) {
                    floatingBadge.style.display = 'none';
                }
            }
        }
        
        // Add to Cart function
        function addToCart(productId) {
            const cart = getCart();
            let productData = {
                id: productId,
                name: '',
                price: 0,
                stock: 0
            };
            
            // Fetch product details from the page
            const productCard = event.target.closest('.product-card');
            if (productCard) {
                productData.name = productCard.querySelector('h5').textContent.trim();
                const priceText = productCard.querySelector('.product-price').textContent;
                productData.price = parseFloat(priceText.replace('tk', '').trim());
            }
            
            // Check if product already in cart
            const existingItem = cart.find(item => item.id == productId);
            
            if (existingItem) {
                // Check stock availability
                fetch(`/api/product/${productId}/`)
                    .then(response => response.json())
                    .then(data => {
                        if (existingItem.quantity < data.stock) {
                            existingItem.quantity += 1;
                            saveCart(cart);
                            showNotification('Product quantity updated in cart!', 'success');
                        } else {
                            showNotification('Maximum stock reached for this product!', 'warning');
                        }
                    })
                    .catch(() => {
                        // If API fails, still allow adding (fallback)
                        existingItem.quantity += 1;
                        saveCart(cart);
                        showNotification('Product quantity updated in cart!', 'success');
                    });
            } else {
                // Try to fetch product data from API first
                fetch(`/api/product/${productId}/`)
                    .then(response => response.json())
                    .then(data => {
                        cart.push({
                            id: productId,
                            name: data.name || productData.name,
                            price: data.price || productData.price,
                            quantity: 1
                        });
                        saveCart(cart);
                        showNotification('Product added to cart!', 'success');
                    })
                    .catch(() => {
                        // Fallback to page data if API fails
                        if (productData.name && productData.price > 0) {
                            cart.push({
                                id: productId,
                                name: productData.name,
                                price: productData.price,
                                quantity: 1
                            });
                            saveCart(cart);
                            showNotification('Product added to cart!', 'success');
                        } else {
                            showNotification('Error: Could not add product to cart. Please try again.', 'danger');
                        }
                    });
            }
        }
        
        function showNotification(message, type = 'success') {
            // Create notification element
            const notification = document.createElement('div');
            notification.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
            notification.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            document.body.appendChild(notification);
            
            // Auto remove after 3 seconds
            setTimeout(() => {
                notification.remove();
            }, 3000);
        }
        
        // Initialize cart badge on page load
        document.addEventListener('DOMContentLoaded', function() {
            updateCartBadge();
        });
        
        // Force apply same orange color to ALL buttons - no conditions
        function applyButtonColors() {
            const buttons = document.querySelectorAll('.btn.btn-product');
            buttons.forEach(function(button) {
                button.style.setProperty('background-color', '#FF9933', 'important');
                button.style.setProperty('color', 'white', 'important');
                button.style.setProperty('border', 'none', 'important');
                button.style.setProperty('opacity', '1', 'important');
            });
        }
        
        // Apply immediately and multiple times to override any rules
        applyButtonColors();
        document.addEventListener('DOMContentLoaded', applyButtonColors);
        setTimeout(applyButtonColors, 50);
        setTimeout(applyButtonColors, 100);
        setTimeout(applyButtonColors, 300);
        setTimeout(applyButtonColors, 500);
        setTimeout(applyButtonColors, 1000);
