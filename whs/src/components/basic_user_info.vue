<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Heart, Pencil, UserRound } from 'lucide-vue-next'
import { useAuth } from '../composables/useAuth'
import { useTips } from '../composables/useTips'
import { copyText } from '../composables/clipboard'

const props = defineProps({
  user: { type: Object, required: true },
})
const emit = defineEmits(['edit-profile', 'follow-changed'])

const { t, locale } = useI18n()
const router = useRouter()
const { state: authState } = useAuth()
const { showTip } = useTips()

const isSelf = computed(() => !!props.user.is_self)
const avatarSrc = computed(() =>
  props.user.avatar ? `/api/user/${props.user.uid}/avatar` : ''
)
const displayName = computed(() => props.user.fullname || props.user.username || '')

// 小字：username | player_name | UID（UID 可点击复制）
const metaItems = computed(() => {
  const items = []
  if (props.user.username) items.push(props.user.username)
  if (props.user.player_name) items.push(props.user.player_name)
  items.push(props.user.uid)
  return items
})

// 关注状态：从 props 初始化，本地维护，避免与父级数据互相干扰
const isFollowing = ref(!!props.user.is_following)
const followersCount = ref(props.user.followers_count || 0)
const followingsCount = ref(props.user.followings_count || 0)
const followLoading = ref(false)

watch(
  () => props.user,
  (u) => {
    if (!u) return
    isFollowing.value = !!u.is_following
    followersCount.value = u.followers_count || 0
    followingsCount.value = u.followings_count || 0
  }
)

function localMessage(data) {
  const m = data && data.message
  if (!m) return t('auth.request_failed')
  return m[locale.value] || m.zh || m.en || ''
}

async function onCopyUid() {
  const ok = await copyText(String(props.user.uid))
  if (ok) showTip('info', t('user.copiedUid'))
  else showTip('error', t('user.copyFailed'))
}

async function onToggleFollow() {
  // 未登录或权限为 0（guest）时不允许关注：提示并跳转登录
  if (!authState.token || (authState.user?.permission ?? 1) < 1) {
    showTip('warning', t('user.followRequiresLogin'))
    router.push('/login')
    return
  }
  if (followLoading.value) return
  followLoading.value = true
  try {
    const action = isFollowing.value ? 'unfollow' : 'follow'
    const res = await fetch(`/api/user/${props.user.uid}/${action}`, {
      method: 'POST',
      headers: authState.token ? { Authorization: `Bearer ${authState.token}` } : {},
    })
    const data = await res.json().catch(() => ({}))
    if (res.ok) {
      isFollowing.value = !!data.is_following
      followersCount.value = data.followers_count
      followingsCount.value = data.followings_count
      emit('follow-changed', {
        is_following: isFollowing.value,
        followers_count: followersCount.value,
        followings_count: followingsCount.value,
      })
    } else {
      showTip('error', localMessage(data))
    }
  } catch (e) {
    showTip('error', t('auth.request_failed'))
    console.warn(e)
  } finally {
    followLoading.value = false
  }
}
</script>

<template>
  <section class="basic-user-info">
    <!-- 左：头像 -->
    <div class="bui-left">
      <img v-if="avatarSrc" :src="avatarSrc" class="bui-avatar" alt="avatar" />
      <span v-else class="bui-avatar bui-avatar-fallback"><UserRound :size="40" /></span>
    </div>

    <!-- 中：大字名称 + 小字 meta -->
    <div class="bui-main">
      <h1 class="bui-name">{{ displayName }}</h1>
      <div class="bui-meta">
        <template v-for="(item, i) in metaItems" :key="i">
          <span
            class="meta-item"
            :class="{ 'uid-clickable': i === metaItems.length - 1 }"
            :title="i === metaItems.length - 1 ? t('user.copiedUid') : ''"
            @click="i === metaItems.length - 1 && onCopyUid()"
          >{{ item }}</span>
          <span v-if="i < metaItems.length - 1" class="meta-sep">|</span>
        </template>
      </div>
    </div>

    <!-- 右：关注/取关 或 修改简介 + 关注统计 -->
    <div class="bui-right">
      <button
        v-if="!isSelf"
        class="follow-btn"
        :class="{ following: isFollowing }"
        :disabled="followLoading"
        @click="onToggleFollow"
      >
        <span v-if="followLoading" class="spinner"></span>
        <Heart v-else :size="18" :fill="isFollowing ? 'currentColor' : 'none'" />
        <span>{{ isFollowing ? t('user.unfollow') : t('user.follow') }}</span>
      </button>
      <button v-else class="follow-btn edit" @click="emit('edit-profile')">
        <Pencil :size="18" />
        <span>{{ t('user.editProfile') }}</span>
      </button>
      <p class="follow-stats">
        {{ followersCount }} {{ t('user.followers') }} · {{ followingsCount }} {{ t('user.followings') }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.basic-user-info {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 24px 28px;
  border-radius: 20px;
  background: var(--card-color);
  border: 1px solid rgba(148, 163, 184, 0.15);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}

.bui-avatar {
  width: 80px;
  height: 80px;
  border-radius: 999px;
  object-fit: cover;
  flex-shrink: 0;
}

.bui-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--btn-hover);
  color: var(--links-color);
}

.bui-main {
  flex: 1;
  min-width: 0;
}

.bui-name {
  margin: 0 0 8px;
  font-size: 32px;
  font-weight: 800;
  color: var(--text-color);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bui-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 14px;
  color: var(--links-color);
}

.meta-item {
  white-space: nowrap;
}

.meta-sep {
  color: var(--links-color);
  opacity: 0.6;
}

.uid-clickable {
  cursor: pointer;
  color: var(--links-color);
  transition: color 0.15s ease;
}

.uid-clickable:hover {
  color: var(--text-color);
  text-decoration: underline;
}

.bui-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.follow-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 999px;
  border: none;
  background: #ebaa28;
  color: #1f2937;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease, opacity 0.2s ease;
}

.follow-btn:hover {
  background: #d99a1f;
}

.follow-btn.following {
  background: var(--btn-hover);
  color: var(--text-color);
}

.follow-btn.edit {
  background: var(--text-color);
  color: var(--bg-color);
}

.follow-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.follow-stats {
  margin: 0;
  font-size: 13px;
  color: var(--links-color);
}

@media (max-width: 768px) {
  .basic-user-info {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
    padding: 20px;
  }

  .bui-right {
    align-items: flex-start;
    width: 100%;
  }

  .follow-btn {
    width: 100%;
    justify-content: center;
  }
}
</style>
