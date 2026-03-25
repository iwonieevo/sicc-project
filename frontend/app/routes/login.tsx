import type { Route } from "./+types/home";
import { Welcome } from "../welcome/welcome";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Sign in | SICC" },
    { name: "description", content: "Sign in to SICC project" },
  ];
}

export default function Login() {
  return <div className="flex items-center justify-center pt-16 pb-4">Sign in to SICC</div>;
}
