/**
 * Pin api.deepseek.com to stable Tencent EdgeOne CDN IP (113.240.66.218)
 * to avoid intermittent TLS handshake failures on secondary edge IP.
 */
const dns = require('node:dns');

const DEEPSEEK_IP = '113.240.66.218';

const origLookup = dns.lookup;
dns.lookup = function (hostname, options, callback) {
  if (typeof options === 'function') {
    callback = options;
    options = {};
  }
  if (hostname === 'api.deepseek.com') {
    if (options && options.all) {
      return callback(null, [{ address: DEEPSEEK_IP, family: 4 }]);
    }
    return callback(null, DEEPSEEK_IP, 4);
  }
  return origLookup.call(dns, hostname, options, callback);
};

if (dns.promises && dns.promises.lookup) {
  const origPromisesLookup = dns.promises.lookup;
  dns.promises.lookup = async function (hostname, options) {
    if (hostname === 'api.deepseek.com') {
      if (options && options.all) {
        return [{ address: DEEPSEEK_IP, family: 4 }];
      }
      return { address: DEEPSEEK_IP, family: 4 };
    }
    return origPromisesLookup.call(dns.promises, hostname, options);
  };
}
