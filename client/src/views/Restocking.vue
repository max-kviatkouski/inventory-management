<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Budget Card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
        </div>
        <div class="budget-body">
          <div class="budget-display">
            <span class="budget-value">{{ formatCurrency(budget) }}</span>
          </div>
          <input
            type="range"
            class="budget-slider"
            :min="0"
            :max="sliderMax"
            :step="step"
            v-model.number="budget"
            :disabled="maxBudget === 0"
            :style="{ '--fill-pct': fillPct + '%' }"
            @change="onBudgetChange"
          />
          <p class="budget-hint">{{ t('restocking.budgetHint') }}</p>
        </div>
      </div>

      <!-- Selected Summary -->
      <div v-if="maxBudget > 0" class="summary-bar">
        <span class="summary-text">
          {{ t('restocking.selectedSummary', {
            count: selectedRecommendations.length,
            cost: formatCurrency(totalSelectedCost),
            budget: formatCurrency(budget)
          }) }}
        </span>
        <button
          class="place-order-btn"
          :disabled="!canPlaceOrder"
          @click="placeOrder"
        >
          {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
        </button>
      </div>

      <!-- Submit success message -->
      <div v-if="submitMessage" class="submit-success">
        {{ submitMessage }}
      </div>

      <!-- Recommendations Card -->
      <div class="card">
        <div class="card-header">
          <div>
            <h3 class="card-title">{{ t('restocking.recommendations') }}</h3>
            <p class="card-subtitle">{{ t('restocking.recommendationsHint') }}</p>
          </div>
        </div>

        <div v-if="recommendations.length === 0 || maxBudget === 0" class="empty-state">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table class="restocking-table">
            <thead>
              <tr>
                <th class="col-sku">{{ t('restocking.table.sku') }}</th>
                <th class="col-name">{{ t('restocking.table.itemName') }}</th>
                <th class="col-demand">{{ t('restocking.table.currentDemand') }}</th>
                <th class="col-demand">{{ t('restocking.table.forecastedDemand') }}</th>
                <th class="col-qty">{{ t('restocking.table.quantity') }}</th>
                <th class="col-cost">{{ t('restocking.table.unitCost') }}</th>
                <th class="col-cost">{{ t('restocking.table.lineCost') }}</th>
                <th class="col-status">{{ t('restocking.table.status') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in recommendations"
                :key="r.item_sku"
                :class="{ 'row-over-budget': !r.in_budget }"
              >
                <td class="col-sku"><strong>{{ r.item_sku }}</strong></td>
                <td class="col-name">{{ r.item_name }}</td>
                <td class="col-demand">{{ r.current_demand }}</td>
                <td class="col-demand">{{ r.forecasted_demand }}</td>
                <td class="col-qty">{{ r.quantity }}</td>
                <td class="col-cost">{{ formatCurrencyWithDecimals(r.unit_cost, currentCurrency, 2) }}</td>
                <td class="col-cost">{{ formatCurrencyWithDecimals(r.line_cost, currentCurrency, 2) }}</td>
                <td class="col-status">
                  <span v-if="r.in_budget" class="badge success">{{ t('restocking.inBudgetBadge') }}</span>
                  <span v-else class="badge">{{ t('restocking.overBudgetBadge') }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency as formatCurrencyUtil, formatCurrencyWithDecimals as formatCurrencyWithDecimalsUtil } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const budget = ref(0)
    const maxBudget = ref(0)
    const recommendations = ref([])
    const submitting = ref(false)
    const submitMessage = ref(null)

    const formatCurrency = (value) => formatCurrencyUtil(value, currentCurrency.value)
    const formatCurrencyWithDecimals = (amount, currency, decimals) =>
      formatCurrencyWithDecimalsUtil(amount, currency, decimals)

    const step = 1

    const sliderMax = computed(() => {
      if (maxBudget.value === 0) return 0
      return Math.ceil(maxBudget.value)
    })

    const fillPct = computed(() =>
      sliderMax.value > 0 ? Math.round((budget.value / sliderMax.value) * 100) : 0
    )

    const selectedRecommendations = computed(() =>
      recommendations.value.filter(r => r.in_budget)
    )

    const totalSelectedCost = computed(() =>
      selectedRecommendations.value.reduce((sum, r) => sum + r.line_cost, 0)
    )

    const canPlaceOrder = computed(() =>
      selectedRecommendations.value.length > 0 && !submitting.value
    )

    const loadRecommendations = async () => {
      error.value = null
      loading.value = true
      try {
        const data = await api.getRestockingRecommendations(budget.value)
        recommendations.value = data.recommendations
        maxBudget.value = data.max_budget
      } catch (err) {
        error.value = t('restocking.error')
        console.error(err)
      } finally {
        loading.value = false
      }
    }

    const onBudgetChange = () => {
      submitMessage.value = null
      loadRecommendations()
    }

    const placeOrder = async () => {
      submitting.value = true
      error.value = null
      try {
        const order = await api.createRestockingOrder(budget.value)
        submitMessage.value = t('restocking.submittedSuccess', { orderNumber: order.order_number })
      } catch (err) {
        error.value = t('restocking.submitError')
        console.error(err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(async () => {
      try {
        // First call: discover max_budget
        const probe = await api.getRestockingRecommendations(0)
        maxBudget.value = probe.max_budget

        if (probe.max_budget === 0) {
          recommendations.value = probe.recommendations
          loading.value = false
          return
        }

        // Initialize budget to max so all items start in-budget
        budget.value = Math.ceil(probe.max_budget)

        // Second call: populate in_budget flags with full budget
        const data = await api.getRestockingRecommendations(budget.value)
        recommendations.value = data.recommendations
        maxBudget.value = data.max_budget
      } catch (err) {
        error.value = t('restocking.error')
        console.error(err)
      } finally {
        loading.value = false
      }
    })

    return {
      t,
      currentCurrency,
      loading,
      error,
      budget,
      maxBudget,
      recommendations,
      submitting,
      submitMessage,
      step,
      sliderMax,
      fillPct,
      selectedRecommendations,
      totalSelectedCost,
      canPlaceOrder,
      formatCurrency,
      formatCurrencyWithDecimals,
      onBudgetChange,
      placeOrder
    }
  }
}
</script>

<style scoped>
/* Budget card body */
.budget-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.5rem 0;
}

.budget-display {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.budget-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.03em;
}

/* Range slider */
.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  cursor: pointer;
}

.budget-slider:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Webkit thumb */
.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 4px rgba(37, 99, 235, 0.4);
  transition: box-shadow 0.15s ease;
}

.budget-slider::-webkit-slider-thumb:hover {
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
}

/* Firefox thumb */
.budget-slider::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #2563eb;
  cursor: pointer;
  border: 2px solid #ffffff;
  box-shadow: 0 1px 4px rgba(37, 99, 235, 0.4);
}

/* Webkit track filled portion */
.budget-slider::-webkit-slider-runnable-track {
  background: linear-gradient(
    to right,
    #2563eb 0%,
    #2563eb var(--fill-pct, 100%),
    #e2e8f0 var(--fill-pct, 100%),
    #e2e8f0 100%
  );
  border-radius: 3px;
  height: 6px;
}

.budget-hint {
  font-size: 0.813rem;
  color: #64748b;
  margin: 0;
}

/* Summary bar */
.summary-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.25rem;
  gap: 1rem;
}

.summary-text {
  font-size: 0.938rem;
  color: #475569;
  font-weight: 500;
}

/* Place Order button */
.place-order-btn {
  flex-shrink: 0;
  background: #2563eb;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.75rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Submit success banner */
.submit-success {
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  color: #059669;
  font-size: 0.938rem;
  font-weight: 500;
  padding: 0.875rem 1.25rem;
  border-radius: 8px;
  margin-bottom: 1.25rem;
}

/* Card subtitle */
.card-subtitle {
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
  font-weight: 400;
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: #64748b;
  font-size: 0.938rem;
}

/* Restocking table */
.restocking-table {
  table-layout: fixed;
  width: 100%;
}

.col-sku {
  width: 110px;
}

.col-name {
  width: 200px;
}

.col-demand {
  width: 130px;
}

.col-qty {
  width: 100px;
}

.col-cost {
  width: 120px;
}

.col-status {
  width: 120px;
}

/* Over-budget row dimming */
.row-over-budget {
  opacity: 0.5;
}

/* Neutral (over-budget) badge */
.badge:not(.success):not(.info):not(.warning):not(.danger) {
  background: #f1f5f9;
  color: #64748b;
}
</style>
