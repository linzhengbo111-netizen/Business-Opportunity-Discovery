import { Link } from "react-router-dom";
import PageMeta from "@/components/common/PageMeta";

export default function NotFound() {
  return (
    <>
      <PageMeta title="页面未找到" description="" />
      <div className="relative flex flex-col items-center justify-center min-h-screen p-6 overflow-hidden z-1">
        <div className="mx-auto w-full max-w-[242px] text-center sm:max-w-[472px]">
          <h1 className="mb-8 font-bold text-gray-800 text-title-md xl:text-title-2xl">
            错误
          </h1>

          <img src="/images/error/404.svg" alt="404" />

          <p className="mt-10 mb-6 text-base text-gray-700 sm:text-lg">
            页面可能已被删除或不存在，请检查网址是否正确。
          </p>

          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-5 py-3.5 text-sm font-medium text-gray-700 shadow-theme-xs hover:bg-gray-50 hover:text-gray-800"
          >
            返回首页
          </Link>
        </div>
        {/* <!-- Footer --> */}
        <p className="absolute text-sm text-center text-gray-500 -translate-x-1/2 bottom-6 left-1/2">
          &copy; {new Date().getFullYear()}
        </p>
      </div>
    </>
  );
}
