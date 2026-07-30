function toggleNav() {
        var sidebar = document.getElementById("sidebar");
        if (sidebar.classList.contains("open")) {
            sidebar.classList.remove("open");
        } else {
            sidebar.classList.add("open");
        }
    }
    function openEditTransactionModal(button) {
      document.getElementById('edit_transaction_id').value = button.getAttribute('data-id');
      document.getElementById('edit_bank_account').value = button.getAttribute('data-bank_account');
      document.getElementById('edit_date').value = button.getAttribute('data-date');
      document.getElementById('edit_narration').value = button.getAttribute('data-narration');
      document.getElementById('edit_transaction_type').value = button.getAttribute('data-transaction_type');
      document.getElementById('edit_amount').value = button.getAttribute('data-amount');
      document.getElementById('editTransactionModal').style.display = 'flex';
      document.getElementById('editTransactionForm').action = `/update_transaction/${button.getAttribute('data-id')}/`;
    }
    function closeEditTransactionModal() {
      document.getElementById('editTransactionModal').style.display = 'none';
    }
    // Optional: Close modal on background click
    document.addEventListener('DOMContentLoaded', function() {
      var editModal = document.getElementById('editTransactionModal');
      if (editModal) {
        editModal.addEventListener('click', function(e) {
          if (e.target === this) closeEditTransactionModal();
        });
      }
    });
