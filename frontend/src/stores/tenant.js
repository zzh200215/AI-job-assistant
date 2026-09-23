import { ref } from 'vue'
import { defineStore } from 'pinia'

import request from '@/api/request'

const CACHE_KEY = 'tenant.brand'

const DEFAULT_BRAND = {
  name: 'Career Signal',
  logo_url: '',
  primary_color: '#2563eb',
  favicon: '',
  login_bg: '',
  company: '',
  contact: '',
}

/** 按百分比调亮/调暗 hex 主色（percent 负值变暗、正值变亮）。 */
function shade(hex, percent) {
  const value = String(hex || '').replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(value)) return hex
  const num = parseInt(value, 16)
  let r = (num >> 16) & 0xff
  let g = (num >> 8) & 0xff
  let b = num & 0xff
  const target = percent < 0 ? 0 : 255
  const p = Math.abs(percent) / 100
  r = Math.round((target - r) * p + r)
  g = Math.round((target - g) * p + g)
  b = Math.round((target - b) * p + b)
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`
}

function loadCached() {
  try {
    const raw = JSON.parse(localStorage.getItem(CACHE_KEY) || 'null')
    return raw && typeof raw === 'object' ? { ...DEFAULT_BRAND, ...raw } : null
  } catch {
    return null
  }
}

function applyCssVariables(brand) {
  if (!brand) return
  const root = document.documentElement
  const primary = brand.primary_color || DEFAULT_BRAND.primary_color
  root.style.setProperty('--app-primary', primary)
  root.style.setProperty('--app-primary-dark', shade(primary, -12))
  root.style.setProperty('--app-primary-light', shade(primary, 88))
  if (brand.login_bg) {
    root.style.setProperty('--app-login-bg', `url("${brand.login_bg}")`)
  }
}

export const useTenantStore = defineStore('tenant', () => {
  /** 品牌配置（未拉取时为 null，前端回退默认）。 */
  const brand = ref(loadCached())
  const loaded = ref(false)

  function apply(payload) {
    const merged =
      payload && typeof payload === 'object'
        ? { ...DEFAULT_BRAND, ...payload }
        : { ...DEFAULT_BRAND }
    brand.value = merged
    applyCssVariables(merged)
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(merged))
    } catch {
      /* ignore quota / private mode */
    }
  }

  async function init() {
    // 先应用缓存品牌，避免默认样式闪一下
    applyCssVariables(brand.value)
    try {
      const data = await request.get('/tenant/brand', { notifyError: false })
      apply(data)
    } catch {
      // 品牌拉取失败时保持默认/缓存，不影响主流程
    } finally {
      loaded.value = true
    }
  }

  return { brand, loaded, init, apply }
})
