export function Navbar() {
    return (
        <nav className="bg-gray-800 text-white p-4">    
            <div className="container mx-auto flex items-center justify-between">
                <div className="text-lg font-bold">SICC Client</div>
                <div className="space-x-4">
                    <a href="/" className="hover:underline">Home</a>
                    <a href="/login" className="hover:underline">Login</a>
                </div>
            </div>
        </nav>
    );
}