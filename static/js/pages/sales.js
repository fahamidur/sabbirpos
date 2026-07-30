function toggleNav() {
      document.getElementById('sidebar').classList.toggle('open');
    }

    var cart = [];

    (function () {
      var el = document.getElementById('saleDateInput');
      if (el && !el.value) el.value = new Date().toISOString().slice(0, 10);
    })();

    function addToCart() {
      var productSelect = document.getElementById('productSelect');
      var quantityInput = document.getElementById('quantityInput');
      var lessInput = document.getElementById('lessInput');
      var selectedOption = productSelect.options[productSelect.selectedIndex];

      if (!selectedOption || selectedOption.value === '') {
        alert('Please select a product.');
        return;
      }
      var productName = selectedOption.text;
      var price = parseFloat(selectedOption.getAttribute('data-price'));
      var quantity = parseFloat(quantityInput.value) || 0;
      if (quantity <= 0) {
        alert('Please enter a valid quantity greater than 0.');
        return;
      }
      var lessPerUnit = parseFloat(lessInput.value) || 0;
      var less = lessPerUnit * quantity;
      var total = (price * quantity) - less;
      var id = selectedOption.getAttribute('data-id');
      cart.push({ product: productName, price: price, quantity: quantity, less: less, lessPerUnit: lessPerUnit, total: total, id: id });
      renderCart();
    }

    function renderCart() {
      var tbody = document.getElementById('cartTableBody');
      tbody.innerHTML = '';
      var grandTotal = 0;
      cart.forEach(function(item, index) {
        var row = document.createElement('tr');
        row.innerHTML = '<td>' + item.product + '</td>' +
          '<td>Tk' + item.price + '</td>' +
          '<td>' + item.quantity + '</td>' +
          '<td><input type="number" class="qty-input" value="' + item.lessPerUnit + '" onchange="updateLess(' + index + ', this.value)" min="0" step="any"></td>' +
          '<td>Tk' + item.total + '</td>' +
          '<td><button type="button" onclick="removeFromCart(' + index + ')" class="btn-remove">Remove</button></td>';
        tbody.appendChild(row);
        grandTotal += item.total;
      });
      document.getElementById('grandTotal').textContent = grandTotal;
      calculateDue();
    }

    function updateLess(index, newLessPerUnit) {
      var item = cart[index];
      item.lessPerUnit = parseFloat(newLessPerUnit) || 0;
      item.less = item.lessPerUnit * item.quantity;
      item.total = (item.price * item.quantity) - item.less;
      renderCart();
    }

    function removeFromCart(index) {
      cart.splice(index, 1);
      renderCart();
    }

    function calculateDue() {
      var grandTotal = 0;
      cart.forEach(function(item) { grandTotal += item.total; });
      document.getElementById('grandTotal').textContent = grandTotal;
      var discountPercentage = parseFloat(document.getElementById('discountInput').value) || 0;
      var lessAmount = parseFloat(document.getElementById('lessAmountInput').value) || 0;
      var discountAmount = grandTotal * discountPercentage / 100;
      var discountedTotal = grandTotal - discountAmount - lessAmount;
      var payment = parseFloat(document.getElementById('paymentInput').value) || 0;
      var due = discountedTotal - payment;
      document.getElementById('dueAmount').textContent = due.toFixed(2);
    }

    function completeSale() {
      if (cart.length === 0) {
        alert('Your cart is empty.');
        return;
      }
      var salesman = document.getElementById('salesmanSelect').value;
      var customer = document.getElementById('customerSelect').value;
      var discount = parseFloat(document.getElementById('discountInput').value) || 0;
      var less = parseFloat(document.getElementById('lessAmountInput').value) || 0;
      var payment_received = parseFloat(document.getElementById('paymentInput').value) || 0;
      var total_price = 0;
      cart.forEach(function(item) { total_price += item.total; });
      var due = parseFloat(document.getElementById('dueAmount').textContent) || 0;
      var dateEl = document.getElementById('saleDateInput');
      var sale_date = (dateEl && dateEl.value) ? String(dateEl.value).trim() : new Date().toISOString().slice(0, 10);
      if (!sale_date) sale_date = new Date().toISOString().slice(0, 10);
      var payload = {
        salesman: salesman,
        customer: customer,
        products: cart,
        total_price: total_price,
        discount: discount,
        less: less,
        payment_received: payment_received,
        due: due,
        sale_date: sale_date
      };
      fetch('/save-sale/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'success') {
          alert('Sale completed and saved!');
          cart = [];
          document.getElementById('paymentInput').value = 0;
          document.getElementById('discountInput').value = 0;
          document.getElementById('lessAmountInput').value = 0;
          renderCart();
        } else {
          alert('Error: ' + data.error);
        }
      })
      .catch(function(err) { alert('Error: ' + err); });
    }

    function showCustomerInfo() {
      var select = document.getElementById('customerSelect');
      var infoDiv = document.getElementById('customerInfo');
      var selected = select.options[select.selectedIndex];
      if (selected && selected.value) {
        var due = selected.getAttribute('data-due') || 0;
        var advance = selected.getAttribute('data-advance') || 0;
        infoDiv.innerHTML = 'Due: Tk ' + parseFloat(due).toFixed(2) + ' &nbsp; | &nbsp; Advance: Tk ' + parseFloat(advance).toFixed(2);
      } else {
        infoDiv.innerHTML = '';
      }
    }

    function onSalesmanChange() {
      var salesmanId = document.getElementById('salesmanSelect').value;
      var url = new URL(window.location.href);
      if (salesmanId) url.searchParams.set('salesman', salesmanId);
      else url.searchParams.delete('salesman');
      window.location.href = url.toString();
    }

    function onLessAmountChange() { calculateDue(); }
    function onPerProductLessChange() { calculateDue(); }
