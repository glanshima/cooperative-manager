"use client";

import HomeView from "@/components/home/HomeView";
import { useHomePage } from "@/components/home/hooks/useHomePage";

export default function Home() {
  const model = useHomePage();

  return <HomeView model={model} />;
}
