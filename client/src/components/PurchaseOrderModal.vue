<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">
              {{ mode === 'create' ? 'Create Purchase Order' : 'Purchase Order Details' }}
            </h3>
            <button class="close-button" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <!-- Item header (shared between create and view) -->
            <div class="item-header">
              <div class="item-icon">
                <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
                  <rect x="4" y="8" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                  <path d="M9 8V6a5 5 0 0110 0v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
              </div>
              <div class="item-title-section">
                <h4 class="item-name">{{ translateProductName(backlogItem.item_name) }}</h4>
                <div class="item-sku">SKU: {{ backlogItem.item_sku }}</div>
              </div>
              <span class="priority-badge" :class="backlogItem.priority">
                {{ backlogItem.priority }} Priority
              </span>
            </div>

            <!-- Create mode: form -->
            <template v-if="mode === 'create'">
              <div v-if="error" class="error">{{ error }}</div>

              <form @submit.prevent="submitForm" class="po-form">
                <div class="form-row">
                  <div class="form-group">
                    <label class="form-label">Supplier Name <span class="required">*</span></label>
                    <input
                      v-model="supplierName"
                      type="text"
                      class="form-input"
                      placeholder="Enter supplier name"
                      required
                    />
                  </div>
                </div>

                <div class="form-row two-col">
                  <div class="form-group">
                    <label class="form-label">Quantity <span class="required">*</span></label>
                    <input
                      v-model.number="quantity"
                      type="number"
                      class="form-input"
                      min="1"
                      required
                    />
                    <div class="form-hint">Shortage: {{ shortage }} units</div>
                  </div>

                  <div class="form-group">
                    <label class="form-label">Unit Cost <span class="required">*</span></label>
                    <input
                      v-model.number="unitCost"
                      type="number"
                      class="form-input"
                      min="0"
                      step="0.01"
                      placeholder="0.00"
                      required
                    />
                  </div>
                </div>

                <div class="form-row">
                  <div class="form-group">
                    <label class="form-label">Expected Delivery Date <span class="required">*</span></label>
                    <input
                      v-model="expectedDeliveryDate"
                      type="date"
                      class="form-input"
                      required
                    />
                  </div>
                </div>

                <div class="form-row">
                  <div class="form-group">
                    <label class="form-label">Notes</label>
                    <textarea
                      v-model="notes"
                      class="form-input form-textarea"
                      placeholder="Optional notes..."
                      rows="3"
                    ></textarea>
                  </div>
                </div>
              </form>
            </template>

            <!-- View mode: read-only info grid -->
            <template v-else>
              <div v-if="poLoading" class="po-loading">Loading purchase order...</div>
              <div v-else-if="poError" class="error">{{ poError }}</div>
              <div v-else-if="poData" class="info-grid">
                <div class="info-item">
                  <div class="info-label">PO ID</div>
                  <div class="info-value po-id">{{ poData.id }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Supplier</div>
                  <div class="info-value">{{ poData.supplier_name }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Quantity</div>
                  <div class="info-value">{{ poData.quantity }} units</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Unit Cost</div>
                  <div class="info-value">{{ formatCurrencyValue(poData.unit_cost) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Expected Delivery</div>
                  <div class="info-value">{{ formatDate(poData.expected_delivery_date) }}</div>
                </div>

                <div class="info-item">
                  <div class="info-label">Status</div>
                  <div class="info-value">
                    <span class="badge" :class="getStatusBadge(poData.status)">{{ poData.status }}</span>
                  </div>
                </div>

                <div class="info-item">
                  <div class="info-label">Created Date</div>
                  <div class="info-value">{{ formatDate(poData.created_date) }}</div>
                </div>

                <div class="info-item full-span">
                  <div class="info-label">Notes</div>
                  <div class="info-value">{{ poData.notes || 'None' }}</div>
                </div>
              </div>
            </template>
          </div>

          <div class="modal-footer">
            <template v-if="mode === 'create'">
              <button class="btn-secondary" @click="close" :disabled="submitting">Cancel</button>
              <button
                class="btn-primary"
                @click="submitForm"
                :disabled="!isFormValid || submitting"
              >
                {{ submitting ? 'Creating...' : 'Create Purchase Order' }}
              </button>
            </template>
            <template v-else>
              <button class="btn-secondary" @click="close">Close</button>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from '../composables/useI18n'
import { api } from '../api'

const { translateProductName } = useI18n()

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false
  },
  backlogItem: {
    type: Object,
    default: null
  },
  mode: {
    type: String,
    default: 'create'
  }
})

const emit = defineEmits(['close', 'po-created'])

// Create mode form state
const supplierName = ref('')
const quantity = ref(0)
const unitCost = ref('')
const expectedDeliveryDate = ref('')
const notes = ref('')
const submitting = ref(false)
const error = ref(null)

// View mode state
const poData = ref(null)
const poLoading = ref(false)
const poError = ref(null)

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return props.backlogItem.quantity_needed - props.backlogItem.quantity_available
})

const isFormValid = computed(() => {
  return (
    supplierName.value.trim() !== '' &&
    quantity.value > 0 &&
    unitCost.value !== '' &&
    Number(unitCost.value) >= 0 &&
    expectedDeliveryDate.value !== ''
  )
})

const resetCreateForm = () => {
  supplierName.value = ''
  quantity.value = shortage.value
  unitCost.value = ''
  expectedDeliveryDate.value = ''
  notes.value = ''
  submitting.value = false
  error.value = null
}

const resetViewState = () => {
  poData.value = null
  poLoading.value = false
  poError.value = null
}

const loadPurchaseOrder = async () => {
  if (!props.backlogItem) return
  poLoading.value = true
  poError.value = null
  try {
    poData.value = await api.getPurchaseOrderByBacklogItem(props.backlogItem.id)
  } catch (err) {
    poError.value = 'Failed to load purchase order details'
    console.error(err)
  } finally {
    poLoading.value = false
  }
}

watch(
  () => props.isOpen,
  (newVal) => {
    if (newVal && props.backlogItem) {
      if (props.mode === 'create') {
        resetCreateForm()
        // Set default quantity to shortage
        quantity.value = shortage.value
      } else {
        resetViewState()
        loadPurchaseOrder()
      }
    } else if (!newVal) {
      resetCreateForm()
      resetViewState()
    }
  }
)

const close = () => {
  emit('close')
}

const submitForm = async () => {
  if (!isFormValid.value || submitting.value) return

  submitting.value = true
  error.value = null
  try {
    const po = await api.createPurchaseOrder({
      backlog_item_id: props.backlogItem.id,
      supplier_name: supplierName.value,
      quantity: Number(quantity.value),
      unit_cost: Number(unitCost.value),
      expected_delivery_date: expectedDeliveryDate.value,
      notes: notes.value || null
    })
    emit('po-created', po)
    resetCreateForm()
  } catch (err) {
    error.value = 'Failed to create purchase order. Please try again.'
    console.error(err)
  } finally {
    submitting.value = false
  }
}

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  // Date-only strings (YYYY-MM-DD) are parsed by `new Date()` as UTC midnight,
  // which shifts the displayed date one day back in UTC-behind timezones.
  // Construct via local-time parts to avoid that shift.
  // Full ISO datetime strings (e.g. "2026-06-22T11:11:04") parse in local time
  // and are handled correctly by the fallback path.
  let date
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateString)) {
    const [year, month, day] = dateString.split('-').map(Number)
    date = new Date(year, month - 1, day)
  } else {
    date = new Date(dateString)
  }
  if (isNaN(date.getTime())) return 'N/A'
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}

const formatCurrencyValue = (value) => {
  if (value === null || value === undefined) return 'N/A'
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value)
}

const getStatusBadge = (status) => {
  if (!status) return ''
  const s = status.toLowerCase()
  if (s === 'delivered' || s === 'completed') return 'success'
  if (s === 'pending' || s === 'processing') return 'warning'
  if (s === 'cancelled') return 'danger'
  return 'info'
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 640px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 1.5rem;
}

.item-icon {
  width: 52px;
  height: 52px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.item-title-section {
  flex: 1;
  min-width: 0;
}

.item-name {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 0.375rem 0;
}

.item-sku {
  font-size: 0.875rem;
  color: #64748b;
  font-family: 'Monaco', 'Courier New', monospace;
}

.priority-badge {
  padding: 0.375rem 0.875rem;
  border-radius: 6px;
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  flex-shrink: 0;
}

.priority-badge.high,
.priority-badge.High {
  background: #fecaca;
  color: #991b1b;
}

.priority-badge.medium,
.priority-badge.Medium {
  background: #fed7aa;
  color: #92400e;
}

.priority-badge.low,
.priority-badge.Low {
  background: #dbeafe;
  color: #1e40af;
}

/* Form styles */
.po-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-row {
  display: flex;
  flex-direction: column;
}

.form-row.two-col {
  flex-direction: row;
  gap: 1rem;
}

.form-row.two-col .form-group {
  flex: 1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-label {
  font-size: 0.813rem;
  font-weight: 600;
  color: #374151;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.required {
  color: #ef4444;
}

.form-input {
  padding: 0.625rem 0.875rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  color: #0f172a;
  background: white;
  font-family: inherit;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  width: 100%;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.form-textarea {
  resize: vertical;
  min-height: 80px;
}

.form-hint {
  font-size: 0.75rem;
  color: #64748b;
}

/* Info grid for view mode */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-item.full-span {
  grid-column: 1 / -1;
}

.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.info-value.po-id {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

/* Status badges */
.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.813rem;
  font-weight: 600;
}

.badge.success {
  background: #dcfce7;
  color: #166534;
}

.badge.warning {
  background: #fef3c7;
  color: #92400e;
}

.badge.danger {
  background: #fee2e2;
  color: #991b1b;
}

.badge.info {
  background: #dbeafe;
  color: #1e40af;
}

/* Loading / error */
.po-loading {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 0.75rem 1rem;
  font-size: 0.875rem;
  margin-bottom: 1rem;
}

/* Footer */
.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary {
  padding: 0.625rem 1.25rem;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  color: #334155;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary:hover:not(:disabled) {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  padding: 0.625rem 1.25rem;
  background: #3b82f6;
  border: 1px solid #2563eb;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
