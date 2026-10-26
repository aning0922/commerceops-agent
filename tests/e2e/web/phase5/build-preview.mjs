// One test-owned entry; no server, external dependency, or product route.
import { createRequire } from "node:module";
import { resolve } from "node:path";
const require = createRequire(import.meta.url);
const root = resolve(import.meta.dirname, "../../../..");
await require(
  resolve(root, "frontend/node_modules/next/dist/build/swc"),
).loadBindings();
const webpack = require(
  resolve(root, "frontend/node_modules/next/dist/compiled/webpack/webpack"),
).webpack;
await new Promise((accept, reject) => {
  const compiler = webpack({
    mode: "production",
    devtool: false,
    optimization: { minimize: false, minimizer: [] },
    context: root,
    plugins: [
      new webpack.DefinePlugin({
        "process.env": JSON.stringify({ NODE_ENV: "production" }),
      }),
    ],
    entry: resolve(import.meta.dirname, "preview.tsx"),
    output: { path: resolve(root, ".audit/p5-source-preview"), filename: "bundle.js" },
    resolve: {
      extensions: [".tsx", ".ts", ".js", ".json"],
      modules: [resolve(root, "frontend/node_modules"), "node_modules"],
    },
    module: {
      rules: [
        {
          test: /\.tsx?$/,
          exclude: /node_modules/,
          use: resolve(root, "tests/e2e/web/phase4/swc-loader.cjs"),
        },
      ],
    },
  });
  compiler.run((error, stats) =>
    compiler.close(() => {
      if (error || stats.hasErrors())
        reject(
          new Error(
            "P5 source component compilation failed: " +
              (error?.message ?? stats.toString({ all: false, errors: true })),
          ),
        );
      else accept();
    }),
  );
});
