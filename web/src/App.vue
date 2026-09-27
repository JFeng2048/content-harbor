<template>
  <el-config-provider :locale="zhCn">
  <div class="app">
    <!-- 全局动作进度条：加载/保存/发布任一进行中就亮 -->
    <div class="top-progress" :class="{ show: hub.loadingList || hub.saving || hub.publishing }" />

    <AppHeader
      :stats="hub.stats"
      :ai-ready="hub.aiReady"
      :loading="hub.loadingList"
      :list-docked="listDocked"
      :view="hub.view"
      :pending-count="hub.pendingHuman.length"
      @open-list="listDrawer = true"
      @switch="hub.switchView($event)"
      @reload="hub.boot()"
      @sync="hub.syncPending()"
      @ai-write="aiDialog = true"
      @new="hub.newArticle()"
    />

    <!-- 写作视图：列表 + 编辑器，干净的两栏 -->
    <main v-if="hub.view === 'write'" class="layout" :class="{ 'docked-list': listDocked }">
      <ArticleList
        v-if="listDocked"
        v-model:keyword="hub.keyword"
        v-model:status="hub.filterStatus"
        :articles="hub.articles"
        :current-id="hub.currentId"
        :loading="hub.loadingList"
        @open="onOpen"
        @new-article="hub.newArticle()"
      />

      <ArticleEditor
        v-if="hub.current"
        :article="hub.current"
        :is-new="!hub.currentId"
        :dirty="hub.dirty"
        :saving="hub.saving"
        @save="hub.save()"
        @touch="hub.dirty = true"
        @publish="wizard = true"
        @sync-update="hub.updateRemote(hub.updatable)"
        @ai-rewrite="onRewrite"
        @ai-polish="onPolish"
      />
      <div v-else class="pane pane-center">
        <EmptyState
          :px="58"
          title="墨迹未干"
          desc="挑一篇接着写，或新起一篇。写完点右上「发布」一发出网。"
        >
          <el-button type="primary" :icon="Plus" @click="hub.newArticle()">起一篇新文</el-button>
          <el-button :icon="MagicStick" @click="aiDialog = true">让 AI 落笔</el-button>
        </EmptyState>
      </div>
    </main>

    <!-- 管理视图：待人工 / 发布记录 / 平台与账号，宽屏三标签 -->
    <main v-else class="layout single">
      <ManagePanel />
    </main>

    <!-- 窄屏：列表改成抽屉 -->
    <el-drawer v-if="!listDocked" v-model="listDrawer" direction="ltr" size="86%" :with-header="false">
      <ArticleList
        v-model:keyword="hub.keyword"
        v-model:status="hub.filterStatus"
        :articles="hub.articles"
        :current-id="hub.currentId"
        :loading="hub.loadingList"
        @open="id => { onOpen(id); listDrawer = false }"
      />
    </el-drawer>

    <PublishWizard v-model="wizard" :platforms="hub.platforms" />

    <AIWriteDialog
      v-model="aiDialog"
      :platforms="hub.platforms"
      :ready="hub.aiReady"
      @done="hub.open($event)"
    />
  </div>
  </el-config-provider>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { Plus, MagicStick } from '@element-plus/icons-vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useHubStore } from '@/stores/hub'
import { api } from '@/api'
import AppHeader from '@/components/AppHeader.vue'
import ArticleList from '@/components/ArticleList.vue'
import ArticleEditor from '@/components/ArticleEditor.vue'
import PublishWizard from '@/components/PublishWizard.vue'
import ManagePanel from '@/components/ManagePanel.vue'
import AIWriteDialog from '@/components/AIWriteDialog.vue'
import EmptyState from '@/components/EmptyState.vue'

const hub = useHubStore()
const { listDocked } = useBreakpoint()

const listDrawer = ref(false)
const wizard = ref(false)
const aiDialog = ref(false)
const refreshing = ref(false)

onMounted(() => hub.boot())

async function onOpen(id) {
  await hub.open(id)
  listDrawer.value = false
}

async function onRewrite() {
  if (!hub.currentId) return
  try {
    const { value } = await ElMessageBox.prompt(
      '例如：多给两个代码示例 / 语气更口语 / 压缩到 800 字',
      'AI 改写', { inputPlaceholder: '改写要求', inputType: 'textarea' }
    )
    await hub.save()
    await api.aiRewrite(hub.currentId, value)
    await hub.open(hub.currentId)
  } catch { /* 用户取消 */ }
}

async function onPolish() {
  if (!hub.currentId) return
  await hub.save()
  await api.aiPolish(hub.currentId)
  await hub.open(hub.currentId)
}

async function onRefresh() {
  try {
    const { value } = await ElMessageBox.prompt(
      '从哪个平台把已发文章抓回本地？', '抓取平台文章',
      { inputPlaceholder: hub.platforms[0]?.id || 'cnblogs' }
    )
    refreshing.value = true
    await hub.refreshPlatform(value.trim())
  } catch { /* 取消 */ }
  finally { refreshing.value = false }
}
</script>

<style scoped lang="scss">
.pane-center {
  align-items: center;
  justify-content: center;
}

.fab {
  position: fixed;
  right: 16px;
  bottom: 20px;
  z-index: 2000;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 11px 20px;
  border-radius: 24px;
  background: var(--accent);
  color: #fff;
  font-size: var(--fs-md);
  font-weight: 500;
  box-shadow: var(--shadow-lg);
  cursor: pointer;
  user-select: none;
  transition: background .18s var(--ease-out), transform .18s var(--ease-out);

  &:hover { background: var(--accent-hi); }
  &:active { transform: scale(.97); }
}
</style>
