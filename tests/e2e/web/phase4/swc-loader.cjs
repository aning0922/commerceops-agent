// Uses the project's already-locked Next compiler for this single UI test bundle.
const swc = require("../../../../frontend/node_modules/next/dist/build/swc");
module.exports = function (source) {
  const done = this.async();
  swc
    .transform(source, {
      filename: this.resourcePath,
      jsc: {
        target: "es2024",
        parser: {
          syntax: "typescript",
          tsx: this.resourcePath.endsWith(".tsx"),
        },
        transform: { react: { runtime: "automatic" } },
      },
      module: { type: "es6" },
    })
    .then((result) => done(null, result.code), done);
};
