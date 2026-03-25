import type { Route } from "./+types/home";
import { Welcome } from "../welcome/welcome";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "SICC" },
    { name: "description", content: "Welcome to SICC project" },
  ];
}

export default function Home() {
  return <Welcome />;
}
