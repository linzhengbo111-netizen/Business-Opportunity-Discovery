import { useEffect } from 'react';
import PageMeta from '@/components/common/PageMeta';

export default function AuthCallbackPage() {
  return (
    <>
      <PageMeta title="飞书登录中..." description="" />
      <div className="flex flex-col items-center justify-center min-h-screen p-6">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-purple-500 border-r-transparent" />
          <p className="mt-4 text-gray-600">飞书登录中...</p>
        </div>
      </div>
    </>
  );
}
