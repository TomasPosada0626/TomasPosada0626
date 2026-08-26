// Local smoke test -- simulates a Vercel request/response so the
// function can be exercised without deploying first.
const handler = require("./api/index.js");

const req = { url: "/api?repos=TomasPosada0626/cucu,TomasPosada0626/opera,TomasPosada0626/Prodexa,TomasPosada0626/epsilon,TomasPosada0626/Neuroroutine&theme=dark" };
const res = {
  setHeader() {},
  status(code) {
    this._status = code;
    return this;
  },
  send(body) {
    process.stdout.write(body);
  },
};

handler(req, res);
