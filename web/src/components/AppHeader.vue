<template>
  <header class="hdr">
    <el-button v-if="!listDocked" text :icon="Menu" @click="$emit('open-list')" />

    <BrandLogo :px="26" />

    <span class="hdr-sep" />

    <!-- 视图切换：写作（列表+编辑器） / 管理（待人工+发布记录+账号） -->
    <div class="view-switch">
      <button class="vs-btn" :class="{ on: view === 'write' }" @click="$emit('switch', 'write')">写作</button>
      <button class="vs-btn" :class="{ on: view === 'manage' }" @click="$emit('switch', 'manage')">
        管理
        <span v-if="pendingCount" class="vs-dot" />
      </button>
    </div>

    <span class="spacer" />

    <!-- 右侧：主操作突出，次操作降噪收敛 -->
    <span class="ai-state" :class="{ on: aiReady }" :title="aiReady ? 'AI 服务已连接' : '未配置 AI，去 config.json 填 AI_API_KEY'">
      <span class="dot" :class="aiReady ? 'ok' : 'off'" />
      <span class="txt">{{ aiReady ? 'AI 就绪' : 'AI 未配置' }}</span>
    </span>

    <!-- 次级动作（刷新 / 同步 / AI 写稿）全部折叠进「更多」，导航区只留一个锚点，避免平铺堆叠 -->
    <el-dropdown trigger="click" @command="onMore">
      <el-button :icon="MoreFilled" text title="更多" class="hdr-more" />
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="reload" :icon="Refresh">刷新</el-dropdown-item>
          <el-dropdown-item command="sync" :disabled="!stats.pending_sync" :icon="Upload">
            同步待更新{{ stats.pending_sync ? `（${stats.pending_sync}）` : '' }}
          </el-dropdown-item>
          <el-dropdown-item command="ai" :icon="MagicStick">AI 写稿</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <span class="hdr-sep" />

    <el-button type="primary" :icon="Plus" @click="$emit('new')">新建</el-button>
  </header>
</template>

<script setup>
import { Menu, Refresh, Upload, MagicStick, Plus, MoreFilled } from '@element-plus/icons-vue'
import BrandLogo from './BrandLogo.vue'

defineProps({
  stats: { type: Object, default: () => ({}) },
  aiReady: Boolean,
  loading: Boolean,
  listDocked: Boolean,
  view: { type: String, default: 'write' },
  pendingCount: { type: Number, default: 0 }
})
const emit = defineEmits(['open-list', 'reload', 'sync', 'ai-write', 'new', 'switch'])

function onMore(cmd) {
  if (cmd === 'reload') emit('reload')
  else if (cmd === 'sync') emit('sync')
  else if (cmd === 'ai') emit('ai-write')
}
</script>

<style scoped lang="scss">
// 视图切换（写作/管理）：极简双钮，当前项亮金下划线
.view-switch {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--line);
  border-radius: 8px;
  .vs-btn {
    border: 0; background: transparent; color: var(--tx-3);
    font-size: var(--fs-sm); padding: 4px 14px; border-radius: 6px;
    cursor: pointer; position: relative;
    white-space: nowrap;
    display: inline-flex; align-items: center; gap: 5px;
    &:hover { color: var(--tx-1); }
    &.on {
      color: var(--tx-1); background: var(--line-soft);
      box-shadow: inset 0 -2px 0 var(--accent-hi);
    }
  }
  .vs-dot {
    width: 6px; height: 6px; border-radius: 50%; background: var(--warn);
  }
}

.pill .sep {
  width: 1px;
  height: 11px;
  background: var(--line);
  margin: 0 3px;
}

.ai-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--tx-3);
  padding: 0 4px;
  white-space: nowrap;

  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    flex-shrink: 0;
    &.ok { background: var(--ok); animation: pulseDot 2.2s infinite; }
    &.off { background: var(--tx-4); }
  }
  &.on .txt { color: var(--tx-2); }
}

// 窄屏：AI 状态只留圆点，把宽度让给「更多/新建」，避免按钮堆叠挤压
@media (max-width: 767px) {
  .ai-state .txt { display: none; }
  .ai-state { padding: 0 2px; }
  .hdr-sep { display: none; }
  .view-switch .vs-btn { padding: 4px 10px; }
}
</style>
