var config = require('./config.json');
var https = require('https');

function apiCall(path, callback, body, method) {
    method = method || 'GET';
    var opts = {
        host :"api.github.com",
        path : path,
        method : method,
        body: body,
        headers: {'user-agent': config.username, 'Authorization': 'token ' + config.token }
    };

    var request = https.request(opts, function(response) {
        var body = '';
        response.on('data',function(chunk){
            body += chunk;
        });
        response.on('end',function(){
            // console.log(body);
            var json = JSON.parse(body);
            callback(json);
        });
    });

    if (body) {
        request.write(JSON.stringify(body));
    }

    request.end();
}

function getRepos(callback) {
    apiCall('/orgs/rust-lang/repos', function(repos) {
        for (var i in repos) {
            callback(repos[i].name);
        }
    })
}

function listHooks(repoName, callback) {
    apiCall('/repos/rust-lang/' + repoName + '/hooks', function(hooks) {
        for (var i in hooks) {
            callback(repoName, hooks[i]);
        }
    })    
}

function maybeEditHook(repoName, hook) {
    if (hook.config.url == 'http://www.ncameron.org/highfive/newpr.py') {
        console.log('edit ' + repoName + ': ' + hook.name);
        var config = hook.config;
        config.url = 'https://www.ncameron.org/highfive/newpr.py';
        var body = { 'config': config };
        apiCall('/repos/rust-lang/' + repoName + '/hooks/' + hook.id, function(result) {
            console.log(result);
        }, body, 'PATCH')    
    }
}

getRepos(function(repoName) { listHooks(repoName, maybeEditHook) });
