import { Link } from "react-router"

import {
    NavigationMenu,
    NavigationMenuItem,
    NavigationMenuLink,
    NavigationMenuList,
    navigationMenuTriggerStyle,
} from "../ui/navigation-menu"

export function DashboardSidebar() {
    return (
        <div className="min-w-48 sticky top-0 self-start">
            <span className="font-bold text-sm mb-2 pt-4 block">
                Navigation
            </span>
            <NavigationMenu className="border-l-2 border-gray-700 pl-2">
                <NavigationMenuList className="flex-col items-start">
                    <NavigationMenuItem>
                        <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
                            <Link to="/dashboard/commands">Commands</Link>
                        </NavigationMenuLink>
                    </NavigationMenuItem>
                    <NavigationMenuItem>
                        <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
                            <Link to="/dashboard/logs">Logs</Link>
                        </NavigationMenuLink>
                    </NavigationMenuItem>
                </NavigationMenuList>
            </NavigationMenu>
        </div>
    )
}