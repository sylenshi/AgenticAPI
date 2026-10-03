<!-- 控制台-概览：用户基本信息、资料修改、余额与兑换码入口 -->

<template>
  <div class="overview-page">
    <header class="page-head">
      <h2>概览</h2>
    </header>

    <!-- 账户资产卡片 -->
    <div class="stat-cards">
      <div class="stat-card stat-accent-green">
        <div class="stat-label">账户余额（元）</div>
        <div class="stat-value stat-value-brand">{{ info?.balance ?? '0.0000' }}</div>
      </div>
      <div class="stat-card stat-accent-orange">
        <div class="stat-label">累计消费（元）</div>
        <div class="stat-value">{{ info?.usedQuota ?? '0.0000' }}</div>
      </div>
      <div class="stat-card stat-accent-violet">
        <div class="stat-label">用户分组</div>
        <div class="stat-value group-value">
          {{ info?.userGroup || '-' }}
          <a-tag v-if="info?.isAdmin" color="arcoblue" size="small">管理员</a-tag>
          <a-tag v-else-if="info?.isGuest" color="gray" size="small">访客</a-tag>
        </div>
      </div>
    </div>

    <!-- 基本信息卡片 -->
    <section class="page-card">
      <h3 class="card-title">基本信息</h3>
      <a-descriptions :column="2" bordered size="medium">
        <a-descriptions-item label="用户名">
          {{ info?.username }}{{ info?.isGuest ? '（访客）' : '' }}
        </a-descriptions-item>
        <a-descriptions-item label="分组">{{ info?.userGroup }}</a-descriptions-item>
        <a-descriptions-item label="注册时间">{{ formatTime(info?.createTime) }}</a-descriptions-item>
        <a-descriptions-item label="最后登录">{{ formatTime(info?.lastLoginTime) }}</a-descriptions-item>
      </a-descriptions>

      <!-- 资料修改 -->
      <a-divider/>
      <h3 class="card-title">修改资料</h3>
      <a-form :model="profileForm" layout="vertical" class="profile-form">
        <div class="profile-form-row">
          <a-form-item label="昵称" class="profile-form-item">
            <a-input v-model="profileForm.nickname" placeholder="设置一个昵称" :max-length="50" allow-clear/>
          </a-form-item>
          <a-form-item label="手机号" class="profile-form-item">
            <a-input v-model="profileForm.phone" placeholder="选填" :max-length="20" allow-clear/>
          </a-form-item>
        </div>
        <a-button type="primary" :loading="saving" @click="handleSaveProfile">
          {{ saving ? '保存中…' : '保存资料' }}
        </a-button>
      </a-form>
    </section>

    <!-- 余额充值入口：跳转兑换码页面（兑换的唯一入口） -->
    <section class="page-card redeem-card">
      <h3 class="card-title">余额充值</h3>
      <p class="redeem-tip">
        余额用于调用中转接口时按量计费（输入/缓存/输出 token 分别计价，详见模型广场各模型定价）。
      </p>
      <a-button type="primary" @click="goRedeem">
        <template #icon><icon-gift/></template>
        去兑换
      </a-button>
    </section>
  </div>
</template>

<script setup lang="ts">
import {computed, onMounted, reactive, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import {useRouter} from 'vue-router'
import {useUserStore} from '@/stores/user'
import {updateProfile} from '@/api/user'
import {getErrorMessage} from '@/api/request'

const userStore = useUserStore()
const info = computed(() => userStore.userInfo)

// 资料编辑表单（进入页面时用当前资料回填）
const profileForm = reactive({
  nickname: '',
  phone: '',
})
const saving = ref(false)

const formatTime = (time: string | null | undefined) =>
  time ? time.replace('T', ' ').slice(0, 19) : '-'

async function handleSaveProfile() {
  saving.value = true
  try {
    const res = await updateProfile({
      nickname: profileForm.nickname.trim(),
      phone: profileForm.phone.trim(),
    })
    // 用服务端返回的最新资料刷新 store，导航栏显示的昵称会立即跟着变
    userStore.userInfo = res.data
    Message.success('资料更新成功')
  } catch (err) {
    Message.error(getErrorMessage(err, '资料更新失败'))
  } finally {
    saving.value = false
  }
}

// 兑换码充值：跳转兑换页（站内唯一兑换入口）
const router = useRouter()

function goRedeem() {
  router.push('/dashboard/redemptioncodes')
}

onMounted(() => {
  profileForm.nickname = info.value?.nickname ?? ''
  profileForm.phone = info.value?.phone ?? ''
  // 刷新页面直接进入控制台时，守卫已确保 userInfo 加载完成，这里兜底再拉一次
  if (!info.value && userStore.token) {
    userStore.fetchUserInfo()
  }
})
</script>

<style scoped>
.overview-page {
  padding: var(--space-5) var(--space-6);
}

.card-title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

.page-card + .page-card {
  margin-top: var(--space-4);
}

.group-value {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-lg);
}

/* 资料表单：两列排布 */
.profile-form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 320px));
  gap: 0 var(--space-5);
}

.redeem-tip {
  margin: 0 0 var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.7;
}

@media (max-width: 768px) {
  .profile-form-row {
    grid-template-columns: 1fr;
  }
}
</style>
