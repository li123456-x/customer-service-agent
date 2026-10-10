<script setup>
import { computed } from "vue";
import { formatMarkdown } from "./messageFormat";

const props = defineProps({ content: { type: String, default: "" }, formatted: { type: Boolean, default: true } });
const html = computed(() => formatMarkdown(props.content));
</script>

<template>
  <div v-if="formatted" class="message-content" v-html="html"></div>
  <p v-else class="message-plain">{{ content }}</p>
</template>
