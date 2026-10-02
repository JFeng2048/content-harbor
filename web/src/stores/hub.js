import { defineStore } from 'pinia'
import { ElMessage, ElNotification, ElMessageBox } from 'element-plus'
import { api } from '@/api'

// 重构第四刀：所有长任务统一走任务引擎（tasks 表），
// 登录/发布/更新/同步/抓取用同一套"提交 → 轮询"逻辑，不再有双轨。
const POLL_MS = 2000

export const useHubStore = defineStore('hub', {
  state: () => ({
    articles: [],
    currentId: null,
    _openGen: 0,       // 切换文章的代际号：晚返回的旧请求直接丢弃（防连点竞态）
    current: null,
    publications: [],
    allPubs: [],        // 全部发布实例（管理视图用，带文章标题）
    platforms: [],
    accounts: [],
    stats: {},
    aiReady: false,
    pendingHuman: [],   // 需要人工处理的发布实例（掘金草稿等人点发布）
    tasks: [],          // 统一任务列表（替代 runs）
    loginTasks: {},     // platform -> {task_id, status}，登录轮询状态
    keyword: '',
    filterStatus: '',
    dirty: false,      // 编辑器有未保存改动
    saving: false,
    publishing: false,
    loadingList: false,
    view: localStorage.getItem('hub_view') || 'write'   // write=写作 / manage=管理
  }),

  getters: {
    filtered() {
      const kw = this.keyword.trim().toLowerCase()
      return this.articles.filter(a => {
        if (this.filterStatus && a.status !== this.filterStatus) return false
        if (!kw) return true
        return (a.title || '').toLowerCase().includes(kw) ||
               (a.summary || '').toLowerCase().includes(kw)
      })
    },
    currentPubs: (s) => s.publications,
    // 已发布过（有 post_id）的平台，原地更新才有意义
    updatable: (s) => s.publications.filter(p => p.post_id).map(p => p.platform),
    // 挂起等人工的任务（统一 waiting_human）
    waitingTasks: (s) => s.tasks.filter(t => t.status === 'waiting_human')
  },

  actions: {
    switchView(v) {
      this.view = v
      localStorage.setItem('hub_view', v)
    },

    async boot() {
      await Promise.all([this.loadStatus(), this.loadPlatforms(), this.loadList(),
                         this.loadPendingHuman(), this.loadTasks()])
      try { this.aiReady = (await api.aiStatus()).ready } catch { this.aiReady = false }
      // 需要人工的任务定时巡检：一旦出现新条目就弹通知
      this._phTimer && clearInterval(this._phTimer)
      this._phLast = this.pendingHuman.length
      this._phTimer = setInterval(() => {
        this.loadPendingHuman(true)
        this.loadTasks(true)
      }, 30000)
    },

    async loadTasks(notify = false) {
      try {
        const list = await api.tasks() || []
        const prevWaiting = new Set(this.tasks
          .filter(t => t.status === 'waiting_human').map(t => t.task_id))
        this.tasks = list
        if (notify) {
          for (const t of list.filter(
            x => x.status === 'waiting_human' && !prevWaiting.has(x.task_id))) {
            ElNotification({
              title: '任务等待人工处理',
              message: `${t.kind} 任务「${t.message || '挂起中'}」→ 到任务中心处理`,
              type: 'warning', duration: 0
            })
          }
        }
      } catch { /* 轮询失败静默 */ }
    },

    // 提交任务 → 轮询到终态。返回 {status, result} 或抛错。
    // 这是唯一的前端任务等待函数，登录/发布/更新都复用它。
    async waitTask(taskId, deadlineMs = 600000, onTick = null) {
      const deadline = Date.now() + deadlineMs
      while (Date.now() < deadline) {
        const t = await api.task(taskId)
        if (onTick) onTick(t)
        if (t.status === 'ok' || t.status === 'failed' || t.status === 'waiting_human') {
          return t
        }
        await new Promise(res => setTimeout(res, POLL_MS))
      }
      throw new Error(`任务超时（${deadlineMs / 1000}s），可到任务中心继续查看`)
    },

    async resumeTask(taskId, approved = true) {
      await api.resumeTask(taskId, approved)
      ElMessage.success(approved ? '已恢复，任务继续执行' : '已放弃该任务')
      await Promise.all([this.loadTasks(), this.loadPendingHuman(),
                         this.loadPubs(), this.loadAllPubs(), this.loadStatus()])
    },

    async loadPendingHuman(notify = false) {
      try {
        const list = await api.pendingHuman() || []
        const prevIds = new Set(this.pendingHuman.map(x => x.platform + x.post_id + x.article_id))
        this.pendingHuman = list
        if (notify) {
          const fresh = list.filter(x => !prevIds.has(x.platform + x.post_id + x.article_id))
          for (const it of fresh) {
            ElNotification({
              title: '需要人工处理',
              message: `「${it.title || '未命名'}」已发到 ${it.platform} 草稿，到「管理 → 需要人工」去完成最后一步`,
              type: 'warning', duration: 0
            })
          }
        }
      } catch { /* 轮询失败静默 */ }
    },

    async loadAllPubs() {
      this.allPubs = await api.publications() || []
    },

    // 登录流程：统一任务语义，任务中心可见
    async startLogin(platform) {
      if (this.loginTasks[platform]?.status === 'running') return
      const t = await api.startLogin(platform)
      this.loginTasks[platform] = { task_id: t.task_id, status: 'running', message: '等待扫码…' }
      this.waitTask(t.task_id, 600000, (st) => {
        this.loginTasks[platform] = { task_id: t.task_id, ...st }
      }).then((st) => {
        this.loginTasks[platform] = { task_id: t.task_id, ...st }
        if (st.status === 'ok') {
          ElMessage.success(`${platform} 登录成功，以后自动复用`)
          this.loadStatus()
        } else if (st.status === 'waiting_human') {
          ElNotification({
            title: `${platform} 需要人工处理`,
            message: st.message || '登录遇到验证码/风控，到任务中心处理',
            type: 'warning', duration: 0
          })
        }
      }).catch(() => {
        this.loginTasks[platform] = { task_id: t.task_id, status: 'failed', message: '登录任务超时' }
      })
    },

    async loadStatus() {
      this.stats = await api.status()
      this.accounts = this.stats.accounts || []
    },

    async loadPlatforms() {
      this.platforms = await api.platforms()
    },

    async loadList() {
      this.loadingList = true
      try { this.articles = await api.listArticles() || [] }
      finally { this.loadingList = false }
    },

    async open(id) {
      if (this.dirty) {
        try {
          await ElMessageBox.confirm(
            '当前文章有未保存的改动，切换会丢失这些改动。确定切换吗？',
            '未保存的改动', { type: 'warning', confirmButtonText: '确定切换', cancelButtonText: '留在这' }
          )
        } catch { return }   // 用户取消，留在当前文章
      }
      const gen = ++this._openGen
      // 先取文成功再切换：请求失败（404/断网）时 current/currentId 保持原文章，
      // 不再出现 id 已切走、正文还是旧文的错位（审查 C4）
      let article
      try { article = await api.getArticle(id) } catch { return }
      if (!article || gen !== this._openGen) return   // 期间又发起了更新的切换，丢弃本次
      this.currentId = id
      this.current = article
      await this.loadPubs()
      if (gen === this._openGen) this.dirty = false
    },

    async loadPubs() {
      const id = this.currentId
      const pubs = id ? (await api.publications(id) || []) : []
      if (id !== this.currentId) return   // 加载期间又切换了文章，丢弃过期发布列表
      this.publications = pubs
    },

    newArticle() {
      this._openGen++          // 作废所有在途的文章切换请求
      this.currentId = null
      this.current = {
        title: '未命名文章',
        content_md: '',
        summary: '',
        tags: '',
        status: 'draft',
        source: 'human'
      }
      this.publications = []
      this.dirty = true
    },

    async save() {
      if (!this.current) return
      this.saving = true
      try {
        if (this.currentId) {
          await api.updateArticle(this.currentId, {
            title: this.current.title,
            content_md: this.current.content_md,
            summary: this.current.summary,
            tags: this.current.tags,
            status: this.current.status
          })
        } else {
          const r = await api.createArticle({
            ...this.current,
            source: 'human'
          })
          this.currentId = r.id
          // 回填 id，否则编辑器标题栏会显示 #undefined
          this.current = { ...this.current, id: r.id }
        }
        this.dirty = false
        ElMessage.success('已保存')
        await Promise.all([this.loadList(), this.loadStatus(), this.loadPubs()])
      } finally { this.saving = false }
    },

    // 发布 = 勾平台 → 点发布 → 轮询任务。发布前自动保存（人的预期：
    // 我点的发布内容必须是我刚写的最新版，不需要"先保存再发布"）
    async publish(platforms, draftOnly, settings = {}) {
      if (!platforms.length) { ElMessage.warning('先选要发到哪些平台'); return null }
      if (!this.currentId) await this.save()
      if (!this.currentId) return null
      this.publishing = true
      try {
        const t = await api.publish(this.currentId, platforms, draftOnly, 'default', settings)
        const done = await this.waitTask(t.task_id, 600000)
        await this.loadTasks()
        const res = done.result || {}
        const rows = Array.isArray(res) ? res : (res.results || [])
        if (done.status === 'waiting_human') {
          const needHuman = rows.filter(x => x.warning) || []
          ElNotification({
            title: '部分平台需要人工收尾',
            message: `已提交到草稿，到「管理 → 需要人工」完成最后一步（${needHuman.map(x => x.platform).join('、') || '详见任务详情'}）`,
            type: 'warning', duration: 0
          })
          await this.loadPendingHuman()
        } else {
          const bad = rows.filter(x => !x.ok)
          if (bad.length === 0) ElMessage.success(`发布成功 ${rows.length} 个平台`)
          else ElMessage.warning(`${bad.length} 个平台失败：${bad.map(b => b.platform).join('、')}`)
        }
        await Promise.all([this.loadPubs(), this.loadStatus(), this.loadList()])
        return done
      } finally { this.publishing = false }
    },

    async updateRemote(platforms) {
      if (!this.currentId) return
      this.publishing = true
      try {
        const t = await api.update(this.currentId, platforms)
        const done = await this.waitTask(t.task_id, 900000)
        await this.loadTasks()
        const res = done.result || {}
        const rows = Array.isArray(res) ? res : (res.results || [])
        const bad = rows.filter(x => !x.ok)
        if (done.status === 'waiting_human') {
          ElNotification({ title: '更新需要人工收尾', type: 'warning', duration: 0,
            message: '到「管理 → 需要人工」处理' })
        } else if (bad.length === 0) ElMessage.success('同步更新完成')
        else ElMessage.warning(`${bad.length} 个平台更新失败`)
        await Promise.all([this.loadPubs(), this.loadAllPubs(), this.loadStatus()])
        return done
      } finally { this.publishing = false }
    },

    async syncPending() {
      const t = await api.syncPending()
      const done = await this.waitTask(t.task_id, 900000)
      await this.loadTasks()
      ElMessage.success('同步完成')
      await Promise.all([this.loadStatus(), this.loadPubs()])
      return done
    },

    async refreshPlatform(pf) {
      const t = await api.refresh(pf)
      const done = await this.waitTask(t.task_id, 300000)
      const res = done.result || {}
      const count = typeof res === 'number' ? res : (res.count || 0)
      ElMessage.success(`抓回 ${count} 篇`)
      await this.loadList()
      return done
    },

    // 人工步骤接管：带登录态的内置有头浏览器打开平台页
    async assistOpen(platform, url) {
      if (!url) { ElMessage.warning('没有可打开的平台页地址'); return }
      const t = await api.assistOpen(platform, url)
      ElMessage.success('已在内置浏览器打开平台页（带登录态）——完成操作后任务自动结束')
      this.waitTask(t.task_id, 900000).then(() => {
        ElMessage.success('平台页已关闭。如还需人工步骤，到任务中心处理')
      }).catch(() => {})
    }
  }
})
