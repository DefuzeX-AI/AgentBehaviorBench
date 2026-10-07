// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "LUdpServerWrapper.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnUdpServerMessageReceived, const FString&, Message, const FString&, SenderEndpoint);

UCLASS(BlueprintType, Blueprintable)
class UE5PROJECT_API ULUdpServerWrapper : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "UDP")
	bool Start(const FString& SocketName, int32 LocalPort);

	UFUNCTION(BlueprintCallable, Category = "UDP")
	static void Stop();

	UFUNCTION(BlueprintCallable, Category = "UDP")
	static bool SendTo(const FString& Message, const FString& RemoteIP, int32 RemotePort);

	UFUNCTION(BlueprintCallable, Category = "UDP")
	static bool IsRunning();

	UFUNCTION(BlueprintCallable, Category = "UDP")
	static FString GetLocalAddress();

	UPROPERTY(BlueprintAssignable, Category = "UDP")
	FOnUdpServerMessageReceived OnMessageReceived;

private:
	UFUNCTION()
	void HandleDataReceived(const FString& Message, const FString& SenderEndpoint) const;
};
