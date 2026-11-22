#include<bits/stdc++.h>
using namespace std;

signed main()
{
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    long long n;
    if(!(cin>>n)) return 0;

    string ans;
    // With d digits in b, the value is (n-b)*10^d+b, decreasing in b.
    for(long long b=1;b<n;b*=10)
    {
        string cur=to_string(n-b)+to_string(b);
        if(cur.size()>ans.size()||(cur.size()==ans.size()&&cur>ans))
            ans=cur;
    }
    cout<<ans<<'\n';
    return 0;
}
