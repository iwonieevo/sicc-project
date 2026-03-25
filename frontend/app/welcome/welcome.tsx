export function Welcome() {
  return (
    <main className="flex items-center justify-center pt-16 pb-4">
      <div className="flex-1 flex flex-col items-center gap-16 min-h-0">
        <header className="flex flex-col items-center gap-9">
          <div className="w-[500px] max-w-[100vw] p-4">
            <h1 className="text-center text-4xl font-bold">SICC Client</h1>
          </div>
        </header>
        <div className="max-w-[300px] w-full space-y-6 px-4 flex flex-col items-center">
          <a href="https://github.com/iwonieevo/sicc-project" target="_blank" className="inline-block bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded">
            View repo
          </a>
        </div>
      </div>
    </main>
  );
}