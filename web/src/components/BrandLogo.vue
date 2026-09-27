<template>
  <span class="brand" :class="{ big: size === 'big' }">
    <svg class="brand-mark" :style="{ width: px + 'px', height: px + 'px' }" viewBox="0 0 48 48" aria-hidden="true">
      <!-- 内容港 mark：圆角方底 + 金色"一"字笔触 + 散落墨点（多平台分发） -->
      <rect x="3" y="3" width="42" height="42" rx="12" fill="var(--surface)" stroke="var(--line-strong)" stroke-width="1" />
      <!-- "一"：横笔，古铜金，微倾斜，像落笔 -->
      <rect x="13" y="21" width="22" height="4.5" rx="2.25"
            fill="var(--accent)" transform="rotate(-3 24 23)" />
      <!-- 墨点：尾迹，暗示内容散到全网 -->
      <circle cx="36" cy="24" r="1.6" fill="var(--accent-hi)" opacity=".85" />
      <circle cx="39.5" cy="26.5" r="1.1" fill="var(--accent)" opacity=".5" />
      <circle cx="42" cy="28.5" r=".8" fill="var(--accent)" opacity=".3" />
    </svg>
    <span v-if="withName" class="brand-txt">
      <span class="brand-name">{{ name }}</span>
      <span v-if="sub" class="brand-sub">{{ sub }}</span>
    </span>
  </span>
</template>

<script setup>
defineProps({
  name: { type: String, default: '内容港' },
  sub: { type: String, default: '内容进港 · 全网分发' },
  px: { type: Number, default: 28 },
  withName: { type: Boolean, default: true },
  size: { type: String, default: '' }
})
</script>

<style scoped>
.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  user-select: none;
}
.brand-txt { display: flex; flex-direction: column; }
.brand-name {
  font-family: var(--font-serif);
  font-size: 16px;
  font-weight: 600;
  letter-spacing: .04em;
  line-height: 1;
  white-space: nowrap;
  color: var(--tx-1);
}
.brand-sub {
  font-family: var(--font-disp);
  font-size: 10px;
  color: var(--accent);
  letter-spacing: .1em;
  margin-top: 4px;
  line-height: 1;
  white-space: nowrap;
}

/* 手机：品牌文字让位给导航与主操作，只留图形标 */
@media (max-width: 767px) {
  .brand-txt { display: none; }
}
</style>
