import { Link } from "react-router"

import {
    NavigationMenu,
    NavigationMenuItem,
    NavigationMenuLink,
    NavigationMenuList,
    navigationMenuTriggerStyle,
} from "./ui/navigation-menu"

export function Navbar() {
    return (
        <header className="flex-0 flex items-center justify-between p-4">
            <span className="font-bold">
                <Link to="/">
                    SICC
                </Link>
            </span>
            <NavigationMenu>
                <NavigationMenuList>
                    <NavigationMenuItem>
                        <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
                            <Link to="/">Home</Link>
                        </NavigationMenuLink>
                    </NavigationMenuItem>
                    <NavigationMenuItem>
                        <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
                            <Link to="/login">Login</Link>
                        </NavigationMenuLink>
                    </NavigationMenuItem>
                    <NavigationMenuItem>
                        <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
                            <Link to="/signup">Sign up</Link>
                        </NavigationMenuLink>
                    </NavigationMenuItem>
                    <NavigationMenuItem>
                        <NavigationMenuLink asChild className={navigationMenuTriggerStyle()}>
                            <Link to="/me">Profile</Link>
                        </NavigationMenuLink>
                    </NavigationMenuItem>
                </NavigationMenuList>
            </NavigationMenu>
        </header>
    )
}