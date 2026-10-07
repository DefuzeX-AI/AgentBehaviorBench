// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"







struct FSColor : FLinearColor
{
	FSColor(const int32& ColorR, const int32& ColorG, const int32& ColorB, const float& Alpha)
	{
		R = ColorR / 255.f;
		G = ColorG / 255.f;
		B = ColorB / 255.f;

		R = R <= 0.04045f ? R / 12.92f : FMath::Pow((R + 0.055f) / 1.055f, 2.4f);
		G = G <= 0.04045f ? G / 12.92f : FMath::Pow((G + 0.055f) / 1.055f, 2.4f);
		B = B <= 0.04045f ? B / 12.92f : FMath::Pow((B + 0.055f) / 1.055f, 2.4f);

		A = Alpha;
	}

	explicit FSColor(const FColor& InColor) : FSColor(InColor.R, InColor.G, InColor.B, 1.f)
	{
		
	}

	FSColor()
	{
		R = 0;
		G = 0;
		B = 0;
		A = 0.f;
	}
};



